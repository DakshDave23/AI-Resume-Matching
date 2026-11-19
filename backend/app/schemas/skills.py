"""Response bodies for the skills autocomplete (design doc §8)."""

from pydantic import BaseModel


class SkillOut(BaseModel):
    id: int
    name: str
    category: str
    is_custom: bool
