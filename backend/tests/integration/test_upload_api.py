"""Steps 20 and 21: upload a batch, parse it in the background, report its progress.

Step 20's "done when": 15 files accepted, 14 parsed, 1 failed with a reason.
Step 21's: the batch's counts and per-file statuses are correct.

The real API and the real database, inside a rolled-back transaction; files go to a
temporary folder and the fake encoder stands in for the model. TestClient runs the
background task before `post()` returns, so the batch is finished by the next line.
"""

import threading
import uuid
from collections.abc import Iterator, Sequence
from contextlib import nullcontext
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import Resume, ResumeChunk, UploadBatch
from app.models.enums import BatchStatus, FileType, ParseStatus
from app.repositories.batches import StoredFile, create_batch
from app.services.nlp.embedder import TextEncoder, Vectors
from app.services.nlp.loader import ModelLoader
from app.services.pipeline import MISSING_FILE, UNEXPECTED_FAILURE, Pipeline
from app.services.storage import FileStore
from tests.fakes import FakeEncoder
from tests.integration.conftest import make_api_app, wire
from tests.integration.factories import make_job
from tests.samples import GROUND_TRUTH, SAMPLES, jd, jd_text

pytestmark = pytest.mark.integration

SCANNED_REASON = "Looks like a scanned image; OCR is not enabled."


@pytest.fixture
def client(seeded_session: Session, store: FileStore) -> Iterator[TestClient]:
    app = wire(make_api_app(seeded_session), seeded_session, store)
    with TestClient(app) as c:
        app.state.model_loader.wait(timeout=5)
        yield c


def new_job(client: TestClient) -> str:
    response = client.post("/api/v1/jobs", json={"text": jd_text(jd("backend_java"))})
    assert response.status_code == 201
    job_id: str = response.json()["id"]
    return job_id


def sample_files() -> list[tuple[str, bytes]]:
    return [
        (r["file"].rsplit("/", 1)[-1], (SAMPLES / r["file"]).read_bytes())
        for r in GROUND_TRUTH["resumes"]
    ]


def upload(client: TestClient, job_id: str, files: Sequence[tuple[str, bytes]]) -> Any:
    return client.post(
        f"/api/v1/jobs/{job_id}/resumes", files=[("files", (n, d)) for n, d in files]
    )


def stored(store: FileStore) -> list[str]:
    return sorted(p.name for p in store.root.iterdir()) if store.root.exists() else []


# --- The whole batch ---------------------------------------------------------------------


def test_the_15_samples_give_14_parsed_and_1_failed(
    client: TestClient, seeded_session: Session, store: FileStore
) -> None:
    job_id = new_job(client)
    response = upload(client, job_id, sample_files())

    assert response.status_code == 202, response.text
    body = response.json()
    assert (body["job_id"], body["total_files"], body["rejected"]) == (job_id, 15, [])
    assert [a["parse_status"] for a in body["accepted"]] == ["queued"] * 15  # at response time
    assert [a["filename"] for a in body["accepted"]] == [n for n, _ in sample_files()]

    batch = seeded_session.get(UploadBatch, uuid.UUID(body["batch_id"]))
    assert batch is not None
    seeded_session.refresh(batch)
    assert (batch.status, batch.processed_files, batch.failed_files) == (
        BatchStatus.COMPLETED_WITH_ERRORS,
        14,
        1,
    )
    assert batch.completed_at is not None

    resumes = seeded_session.scalars(select(Resume).where(Resume.batch_id == batch.id)).all()
    failed = [r for r in resumes if r.parse_status == ParseStatus.FAILED]
    assert [(r.original_filename, r.parse_error) for r in failed] == [
        ("15_scanned_pdf.pdf", SCANNED_REASON)
    ]
    for resume in resumes:
        if resume.parse_status == ParseStatus.PARSED:
            chunks = seeded_session.scalar(
                select(func.count()).where(ResumeChunk.resume_id == resume.id)
            )
            assert chunks and resume.embedding is not None, resume.original_filename
    # Every file is on disk under its UUID name, never the recruiter's.
    assert stored(store) == sorted(r.storage_path for r in resumes)


def test_a_clean_batch_is_completed(client: TestClient, seeded_session: Session) -> None:
    body = upload(client, new_job(client), sample_files()[:2]).json()
    batch = seeded_session.get(UploadBatch, uuid.UUID(body["batch_id"]))
    assert batch is not None
    seeded_session.refresh(batch)
    assert (batch.status, batch.processed_files, batch.failed_files) == (
        BatchStatus.COMPLETED,
        2,
        0,
    )


# --- Rejected at upload ----------------------------------------------------------------------


def test_bad_files_are_rejected_with_reasons_and_the_rest_go_on(
    client: TestClient, store: FileStore
) -> None:
    good_name, good = sample_files()[0]
    response = upload(
        client,
        new_job(client),
        [
            ("C:\\Users\\asha\\Desktop\\" + good_name, good),
            ("fake.pdf", b"just text pretending to be a PDF"),
            ("notes.txt", b"Java developer with 5 years of experience"),
            ("empty.docx", b""),
            ("copy-of-the-first.pdf", good),
        ],
    )

    assert response.status_code == 202
    body = response.json()
    assert body["total_files"] == 1
    assert [a["filename"] for a in body["accepted"]] == [good_name]
    assert [(r["filename"], r["code"]) for r in body["rejected"]] == [
        ("fake.pdf", "unsupported_type"),
        ("notes.txt", "unsupported_type"),
        ("empty.docx", "empty_file"),
        ("copy-of-the-first.pdf", "duplicate_file"),
    ]
    assert all(r["message"] for r in body["rejected"])
    assert len(stored(store)) == 1


def test_when_no_file_is_usable_nothing_is_kept(
    client: TestClient, seeded_session: Session, store: FileStore
) -> None:
    job_id = new_job(client)
    response = upload(client, job_id, [("a.pdf", b"nope"), ("b.exe", b"MZ")])

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "no_valid_files"
    assert [d["filename"] for d in error["details"]] == ["a.pdf", "b.exe"]
    assert stored(store) == []
    batches = seeded_session.scalar(
        select(func.count()).where(UploadBatch.job_id == uuid.UUID(job_id))
    )
    assert batches == 0


def test_too_many_files(seeded_session: Session, store: FileStore) -> None:
    app = wire(make_api_app(seeded_session), seeded_session, store)
    app.dependency_overrides[get_settings] = lambda: Settings(max_batch_files=2)
    with TestClient(app) as client:
        app.state.model_loader.wait(timeout=5)
        response = upload(client, new_job(client), sample_files()[:3])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "too_many_files"
    assert stored(store) == []


def test_an_unknown_job_is_404(client: TestClient, store: FileStore) -> None:
    response = upload(client, str(uuid.uuid4()), sample_files()[:1])
    assert response.status_code == 404
    assert stored(store) == []


def test_uploading_needs_the_model(seeded_session: Session, store: FileStore) -> None:
    ready = wire(make_api_app(seeded_session), seeded_session, store)
    with TestClient(ready) as client:
        ready.state.model_loader.wait(timeout=5)
        job_id = new_job(client)

    release = threading.Event()

    def slow_load() -> TextEncoder:
        release.wait(timeout=10)
        return FakeEncoder()

    loading = wire(make_api_app(seeded_session, ModelLoader(slow_load)), seeded_session, store)
    with TestClient(loading) as client:
        response = upload(client, job_id, sample_files()[:1])
        release.set()
    assert response.status_code == 503
    assert stored(store) == []


# --- The pipeline on its own ------------------------------------------------------------------


class FailsOnOneResume:
    """An encoder that breaks while embedding sample 1 (Acme Fintech), like a bug would."""

    model_name = "fails-on-one"

    def encode(self, texts: Sequence[str]) -> Vectors:
        if any("Acme Fintech" in t for t in texts):
            raise RuntimeError("boom")
        return FakeEncoder().encode(texts)


def queued_batch(session: Session, store: FileStore, names: list[str]) -> tuple[uuid.UUID, Any]:
    """A batch whose files are stored and queued, but whose pipeline never ran."""
    job = make_job()
    session.add(job)
    session.flush()
    files = []
    for name in names:
        data = (SAMPLES / "resumes" / name).read_bytes()
        kind = FileType(name.rsplit(".", 1)[-1])
        sha = uuid.uuid4().hex * 2
        files.append(StoredFile(name, store.save(data, kind.value), kind, len(data), sha))
    batch, resumes = create_batch(session, job.id, files)
    # Committed (to a savepoint): each API request discards whatever is uncommitted.
    session.commit()
    return batch.id, resumes


def pipeline(session: Session, store: FileStore, encoder: TextEncoder | None = None) -> Pipeline:
    return Pipeline(lambda: nullcontext(session), store, encoder or FakeEncoder(), region="IN")


def statuses(session: Session, batch_id: uuid.UUID) -> list[tuple[str, ParseStatus, str | None]]:
    rows = session.execute(
        select(Resume.original_filename, Resume.parse_status, Resume.parse_error)
        .where(Resume.batch_id == batch_id)
        .order_by(Resume.original_filename)
    ).all()
    session.expire_all()
    return [tuple(row) for row in rows]  # type: ignore[misc]


def test_an_unexpected_error_fails_one_file_and_the_next_goes_on(
    seeded_session: Session, store: FileStore
) -> None:
    batch_id, _ = queued_batch(
        seeded_session, store, ["01_senior_java_engineer.pdf", "02_java_aliases.docx"]
    )
    pipeline(seeded_session, store, FailsOnOneResume()).run_batch(batch_id)

    assert statuses(seeded_session, batch_id) == [
        ("01_senior_java_engineer.pdf", ParseStatus.FAILED, UNEXPECTED_FAILURE),
        ("02_java_aliases.docx", ParseStatus.PARSED, None),
    ]
    batch = seeded_session.get(UploadBatch, batch_id)
    assert batch is not None
    assert (batch.status, batch.processed_files, batch.failed_files) == (
        BatchStatus.COMPLETED_WITH_ERRORS,
        1,
        1,
    )


def test_a_missing_file_fails_with_a_reason(seeded_session: Session, store: FileStore) -> None:
    batch_id, resumes = queued_batch(seeded_session, store, ["01_senior_java_engineer.pdf"])
    store.delete(resumes[0].storage_path)

    pipeline(seeded_session, store).run_batch(batch_id)

    assert statuses(seeded_session, batch_id) == [
        ("01_senior_java_engineer.pdf", ParseStatus.FAILED, MISSING_FILE)
    ]


def test_batches_interrupted_by_a_restart_are_finished(
    seeded_session: Session, store: FileStore
) -> None:
    batch_id, resumes = queued_batch(
        seeded_session, store, ["01_senior_java_engineer.pdf", "02_java_aliases.docx"]
    )
    resumes[0].parse_status = ParseStatus.PARSING  # the server died while parsing this one
    seeded_session.commit()

    assert pipeline(seeded_session, store).resume_unfinished() >= 1

    assert [s for _, s, _ in statuses(seeded_session, batch_id)] == [ParseStatus.PARSED] * 2
    batch = seeded_session.get(UploadBatch, batch_id)
    assert batch is not None and batch.status == BatchStatus.COMPLETED


def test_running_a_finished_batch_again_changes_nothing(
    seeded_session: Session, store: FileStore
) -> None:
    batch_id, resumes = queued_batch(seeded_session, store, ["02_java_aliases.docx"])
    run = pipeline(seeded_session, store)
    run.run_batch(batch_id)
    run.run_batch(batch_id, [r.id for r in resumes])  # e.g. a duplicate background task

    batch = seeded_session.get(UploadBatch, batch_id)
    assert batch is not None
    assert (batch.processed_files, batch.failed_files) == (1, 0)  # not counted twice


# --- Batch progress (step 21) ---------------------------------------------------------


def batch_status(client: TestClient, batch_id: uuid.UUID | str) -> dict[str, Any]:
    response = client.get(f"/api/v1/batches/{batch_id}")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body: dict[str, Any] = response.json()
    return body


def test_batch_counts_and_file_statuses_are_correct(client: TestClient) -> None:
    """Step 21's "done when", on the 15 samples."""
    batch_id = upload(client, new_job(client), sample_files()).json()["batch_id"]

    progress = batch_status(client, batch_id)

    counts = {k: progress[k] for k in ("status", "total_files", "processed_files", "failed_files")}
    assert counts == {
        "status": "completed_with_errors",
        "total_files": 15,
        "processed_files": 14,
        "failed_files": 1,
    }
    assert progress["pending_files"] == 0 and progress["completed_at"] is not None
    files = progress["files"]
    assert [f["filename"] for f in files] == sorted(n for n, _ in sample_files())
    by_name = {f["filename"]: f for f in files}
    scanned = by_name.pop("15_scanned_pdf.pdf")
    assert (scanned["parse_status"], scanned["parse_error"], scanned["candidate_name"]) == (
        "failed",
        SCANNED_REASON,
        None,
    )
    expected_names = {r["file"].rsplit("/", 1)[-1]: r["name"] for r in GROUND_TRUTH["resumes"]}
    for name, f in by_name.items():
        assert (f["parse_status"], f["parse_error"], f["needs_review"]) == ("parsed", None, False)
        assert f["candidate_name"] == expected_names[name]
    assert by_name["10_no_dates.docx"]["parse_confidence"] == 0.83  # no dated role
    assert sum(f["parse_status"] == "parsed" for f in files) == progress["processed_files"]


def test_progress_while_a_batch_is_parsing(
    client: TestClient, seeded_session: Session, store: FileStore
) -> None:
    batch_id, resumes = queued_batch(
        seeded_session, store, ["01_senior_java_engineer.pdf", "02_java_aliases.docx"]
    )

    queued = batch_status(client, batch_id)
    assert (queued["status"], queued["pending_files"], queued["completed_at"]) == (
        "processing",
        2,
        None,
    )
    assert {
        (f["parse_status"], f["parse_error"], f["parse_confidence"], f["candidate_name"])
        for f in queued["files"]
    } == {("queued", None, None, None)}

    pipeline(seeded_session, store).run_resume(batch_id, resumes[0].id)

    halfway = batch_status(client, batch_id)
    assert (halfway["status"], halfway["processed_files"], halfway["pending_files"]) == (
        "processing",
        1,
        1,
    )
    assert [f["parse_status"] for f in halfway["files"]] == ["parsed", "queued"]


def test_a_low_confidence_resume_needs_review(
    client: TestClient, seeded_session: Session, store: FileStore
) -> None:
    batch_id, resumes = queued_batch(seeded_session, store, ["02_java_aliases.docx"])
    resume = resumes[0]
    resume.parse_status, resume.parse_confidence = ParseStatus.PARSED, Decimal("0.33")
    resume.parsed_at = datetime.now(UTC)
    seeded_session.commit()

    (file,) = batch_status(client, batch_id)["files"]
    assert (file["parse_confidence"], file["needs_review"]) == (0.33, True)


def test_an_unknown_batch_is_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/batches/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Batch not found"


def test_polling_never_reads_resume_text_or_vectors(
    client: TestClient, seeded_session: Session
) -> None:
    batch_id = upload(client, new_job(client), sample_files()[:3]).json()["batch_id"]
    statements: list[str] = []

    def record(*args: Any) -> None:
        statements.append(args[2])  # (conn, cursor, statement, parameters, context, many)

    connection = seeded_session.connection()
    event.listen(connection, "before_cursor_execute", record)
    try:
        batch_status(client, batch_id)
    finally:
        event.remove(connection, "before_cursor_execute", record)

    sql = "\n".join(statements).lower()
    assert "raw_text" not in sql and "embedding" not in sql and "parsed_json" not in sql
    assert len(statements) <= 3
