"""restrict skills.category to the taxonomy categories

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-18

Replaces the "not blank" check from 0001 with the real category list, now
that the taxonomy (step 6) has settled it. The skills table is empty or holds
only seeded rows at this point, so validating the new constraint is instant.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copy of app.models.enums.SkillCategory at the time of this migration.
CATEGORIES = (
    "language",
    "framework",
    "library",
    "database",
    "messaging",
    "cloud",
    "devops",
    "tool",
    "data",
    "ml",
    "testing",
    "concept",
    "methodology",
    "soft",
    "business",
)


# op.f() marks a name as final; without it the naming convention in
# app.models.base would prefix it again ("ck_skills_ck_skills_...").


def upgrade() -> None:
    op.drop_constraint(op.f("ck_skills_category_not_blank"), "skills", type_="check")
    category_list = ", ".join(f"'{c}'" for c in CATEGORIES)
    op.create_check_constraint(
        op.f("ck_skills_category_valid"), "skills", f"category IN ({category_list})"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_skills_category_valid"), "skills", type_="check")
    op.create_check_constraint(
        op.f("ck_skills_category_not_blank"), "skills", "length(btrim(category)) > 0"
    )
