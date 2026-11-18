"""The background pipeline: parse every resume of a batch (design doc §2, steps 3-5).

For each resume, in its own transaction:

    queued -> parsing -> extract -> parse -> chunk -> embed -> save -> parsed
                                                     (any failure) -> failed, with a reason

A bad file never fails the batch: its row says why, and the next file goes on.
The batch's counters move in the same transaction as the resume's status, and the
last resume completes the batch.

It is one plain function on purpose: FastAPI's BackgroundTasks runs it today
(in the thread pool, so CPU-bound encoding never blocks the event loop), and
moving to RQ or Celery later means calling it from a worker instead.
"""

import logging
import time
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from app.models import Resume
from app.models.enums import ParseStatus
from app.repositories.batches import count_result, pending_resume_ids, unfinished_batch_ids
from app.repositories.resumes import mark_failed, save_parsed_resume
from app.services.extraction import ExtractionError, extract_text
from app.services.nlp.embedder import TextEncoder
from app.services.nlp.vectors import embed_resume
from app.services.parsing.chunker import chunk_resume
from app.services.parsing.resume_parser import parse_resume
from app.services.storage import FileStore

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], AbstractContextManager[Session]]

# Shown to the recruiter; the details go to the server log.
UNEXPECTED_FAILURE = "Something went wrong while reading this file. Try uploading it again."
MISSING_FILE = "The uploaded file is missing from storage. Upload it again."


@dataclass(frozen=True)
class Pipeline:
    sessions: SessionFactory
    store: FileStore
    encoder: TextEncoder
    region: str  # default phone region
    today: Callable[[], date] = field(default=date.today)  # what "Present" means

    def run_batch(self, batch_id: uuid.UUID, resume_ids: list[uuid.UUID] | None = None) -> None:
        """Parse the given resumes (default: every unfinished one) of a batch, in order."""
        if resume_ids is None:
            with self.sessions() as session:
                resume_ids = pending_resume_ids(session, batch_id)
        started = time.perf_counter()
        for resume_id in resume_ids:
            self.run_resume(batch_id, resume_id)
        logger.info(
            "Batch %s: %d file(s) in %.1f s",
            batch_id,
            len(resume_ids),
            time.perf_counter() - started,
        )
        # Step 26 adds: score every parsed resume of the batch against the job (§2, step 5).

    def run_resume(self, batch_id: uuid.UUID, resume_id: uuid.UUID) -> ParseStatus | None:
        """Parse one resume and count it on its batch. Returns its final status."""
        with self.sessions() as session:
            resume = session.get(Resume, resume_id)
            if resume is None or resume.parse_status in (ParseStatus.PARSED, ParseStatus.FAILED):
                return None  # deleted meanwhile, or already done before a restart
            resume.parse_status = ParseStatus.PARSING
            session.commit()

            try:
                self._parse(session, resume)
            except ExtractionError as exc:  # unreadable, scanned, encrypted: the file's fault
                session.rollback()
                mark_failed(resume, exc.message)
            except FileNotFoundError:
                session.rollback()
                logger.error("Resume %s: stored file %s is missing", resume.id, resume.storage_path)
                mark_failed(resume, MISSING_FILE)
            except Exception:  # a bug or an outage: log it, tell the recruiter plainly
                session.rollback()
                logger.exception(
                    "Resume %s (%s) failed to parse", resume.id, resume.original_filename
                )
                mark_failed(resume, UNEXPECTED_FAILURE)

            status = resume.parse_status
            count_result(session, batch_id, parsed=status == ParseStatus.PARSED)
            session.commit()
            return status

    def _parse(self, session: Session, resume: Resume) -> None:
        data = self.store.read(resume.storage_path)
        text = extract_text(data, resume.file_type.value).text
        today = self.today()
        parsed = parse_resume(text, today=today, region=self.region)
        chunks = chunk_resume(parsed.sections, parsed.work)
        vectors = embed_resume(chunks, parsed.work.roles, self.encoder)
        save_parsed_resume(
            session, resume, text=text, parsed=parsed, chunks=chunks, vectors=vectors, today=today
        )

    def resume_unfinished(self) -> int:
        """Finish batches a restart interrupted (a crash, or `uvicorn --reload` mid-batch).

        Safe because each resume's status and its batch count change in one
        transaction: whatever is still queued or parsing was never counted.
        """
        with self.sessions() as session:
            batch_ids = unfinished_batch_ids(session)
        for batch_id in batch_ids:
            logger.info("Resuming unfinished batch %s", batch_id)
            self.run_batch(batch_id)
        return len(batch_ids)
