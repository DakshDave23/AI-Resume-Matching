"""The original resume file, for reading next to its analysis (design doc §8)."""

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_file_store
from app.core.database import get_db
from app.core.errors import AppError
from app.models import Resume
from app.models.enums import FileType
from app.services.storage import FileStore

router = APIRouter(prefix="/resumes", tags=["resumes"])

MEDIA_TYPES = {
    FileType.PDF: "application/pdf",
    FileType.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.get(
    "/{resume_id}/file",
    summary="The uploaded file, under the recruiter's original file name",
    response_class=FileResponse,
    responses={
        200: {"content": {media: {} for media in MEDIA_TYPES.values()}},
        404: {"description": "No such resume, or its file is gone"},
    },
)
def get_resume_file(
    resume_id: uuid.UUID,
    db: Session = Depends(get_db),
    store: FileStore = Depends(get_file_store),
) -> FileResponse:
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise AppError(404, "Resume not found")
    path = store.path(resume.storage_path)  # a stored <uuid>.<ext> name, never user input
    if not path.is_file():
        raise AppError(404, "The resume's file is no longer stored")
    return FileResponse(
        path,
        media_type=MEDIA_TYPES[resume.file_type],
        filename=resume.original_filename,
        content_disposition_type="inline",  # PDFs open in the browser; DOCX downloads
        headers={"X-Content-Type-Options": "nosniff"},
    )
