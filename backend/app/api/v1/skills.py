"""Taxonomy autocomplete for the requirement chip editor (design doc §8)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.repositories.skills import search_skills
from app.schemas.skills import SkillOut

router = APIRouter(tags=["skills"])


@router.get("/skills", response_model=list[SkillOut], summary="Search skills by name or alias")
def get_skills(
    q: Annotated[str, Query(min_length=1, max_length=100, description="Name or alias")],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    db: Session = Depends(get_db),
) -> list[SkillOut]:
    return [
        SkillOut(id=s.id, name=s.canonical_name, category=s.category, is_custom=s.is_custom)
        for s in search_skills(db, q, limit=limit)
    ]
