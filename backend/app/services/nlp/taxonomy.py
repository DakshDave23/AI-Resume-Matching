"""Load and validate the curated skills taxonomy (design doc §5.2).

The JSON file is the source of truth for seeded skills. Validation runs on
load, so a bad edit (two skills claiming the alias "spark", an unknown
category) fails fast with every problem listed, not at match time.
"""

import re
import unicodedata
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator, model_validator

from app.models.enums import SkillCategory

TAXONOMY_PATH = Path(__file__).resolve().parents[2] / "data" / "skills_taxonomy.json"

_WHITESPACE = re.compile(r"\s+")


def normalize_term(term: str) -> str:
    """Canonical lookup form of a skill name or alias: NFKC, lower case, single spaces."""
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", term)).strip().lower()


class TaxonomySkill(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    category: SkillCategory
    aliases: tuple[str, ...] = ()

    @field_validator("aliases")
    @classmethod
    def _normalize_aliases(cls, aliases: tuple[str, ...]) -> tuple[str, ...]:
        seen: dict[str, None] = {}  # ordered set
        for alias in aliases:
            normalized = normalize_term(alias)
            if normalized:
                seen.setdefault(normalized)
        return tuple(seen)

    @model_validator(mode="after")
    def _drop_alias_equal_to_name(self) -> Self:
        key = normalize_term(self.name)
        if key in self.aliases:
            object.__setattr__(self, "aliases", tuple(a for a in self.aliases if a != key))
        return self

    @property
    def terms(self) -> tuple[str, ...]:
        """Every normalized string that should map to this skill."""
        return (normalize_term(self.name), *self.aliases)


class Taxonomy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str
    skills: tuple[TaxonomySkill, ...]

    @model_validator(mode="after")
    def _every_term_maps_to_one_skill(self) -> Self:
        owners: dict[str, list[str]] = defaultdict(list)
        for skill in self.skills:
            for term in skill.terms:
                owners[term].append(skill.name)

        clashes = [
            f"{term!r} is claimed by {' and '.join(names)}"
            for term, names in sorted(owners.items())
            if len(names) > 1
        ]
        if clashes:
            raise ValueError(
                f"{len(clashes)} ambiguous term(s) in the taxonomy:\n  " + "\n  ".join(clashes)
            )
        return self

    def term_index(self) -> dict[str, TaxonomySkill]:
        """Normalized name or alias -> skill. Unambiguous by construction."""
        return {term: skill for skill in self.skills for term in skill.terms}


def load_taxonomy(path: Path = TAXONOMY_PATH) -> Taxonomy:
    """Parse and validate a taxonomy file. Raises pydantic.ValidationError on any problem."""
    return Taxonomy.model_validate_json(path.read_text(encoding="utf-8"))


@lru_cache
def get_taxonomy() -> Taxonomy:
    """The bundled taxonomy, parsed once per process."""
    return load_taxonomy()
