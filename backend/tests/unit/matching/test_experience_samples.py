"""Step 24's "done when": persona 8 gets about 1.5 relevant years (real model, real samples).

Every relevant-experience figure in ground_truth.json is checked: persona 3 (Candidate
A, the design doc's 4.5 relevant years), 4 (the internship is not counted) and 8 (the
QA years are not counted).
"""

from functools import cache

import pytest

from app.models.enums import RequirementCategory
from app.services.matching.experience import ExperienceScore, experience_score, role_profile
from app.services.matching.inputs import roles_from_parse
from app.services.nlp.embedder import Embedder
from app.services.nlp.vectors import embed_resume
from app.services.parsing.chunker import chunk_resume
from app.services.parsing.jd_parser import parse_job
from app.services.parsing.resume_parser import parse_resume
from tests.samples import AS_OF, TEXT_RESUMES, jd, jd_text, resume_text, text_resume

pytestmark = pytest.mark.model

LABELLED = [
    (r["id"], jd_key, months)
    for r in TEXT_RESUMES
    for jd_key, months in (r["relevant_experience_months"] or {}).items()
]


@cache
def _experience(jd_key: str, persona: int, embedder: Embedder) -> ExperienceScore:
    job = parse_job(jd_text(jd(jd_key)))
    responsibilities = [
        r.text for r in job.requirements if r.category == RequirementCategory.RESPONSIBILITY
    ]
    profile = role_profile(job.title or "", responsibilities, embedder)
    parsed = parse_resume(resume_text(text_resume(persona)), today=AS_OF, region="IN")
    vectors = embed_resume(chunk_resume(parsed.sections, parsed.work), parsed.work.roles, embedder)
    work = parsed.work
    return experience_score(
        profile,
        roles_from_parse(parsed, vectors.roles),
        today=AS_OF,
        min_years=job.min_experience_years,
        total_months=work.total_months,
        stated_months=work.total_months if work.source == "summary_statement" else None,
    )


def test_persona_8_has_one_and_a_half_relevant_years(real_embedder: Embedder) -> None:
    result = _experience("backend_java", 8, real_embedder)
    assert result.relevant_years == 1.5
    qa, backend = sorted(result.roles, key=lambda r: r.factor)
    assert (qa.title, qa.factor) == ("QA Automation Engineer", 0.0)  # 42 months, not counted
    assert (backend.title, backend.factor) == ("Backend Developer", 1.0)
    assert result.score == pytest.approx(1.5 / 4)


@pytest.mark.parametrize(("persona", "jd_key", "months"), LABELLED, ids=lambda v: str(v))
def test_relevant_months_match_the_ground_truth(
    persona: int, jd_key: str, months: int, real_embedder: Embedder
) -> None:
    assert _experience(jd_key, persona, real_embedder).relevant_months == months


@pytest.mark.parametrize("persona", [12, 13], ids=["data-scientist", "accountant"])
def test_unrelated_careers_have_no_relevant_years(persona: int, real_embedder: Embedder) -> None:
    result = _experience("backend_java", persona, real_embedder)
    assert (result.relevant_months, result.score) == (0, 0.0)


def test_overlapping_roles_are_not_counted_twice(real_embedder: Embedder) -> None:
    """Persona 9's freelance years (2022-2023) sit inside the bank job (2020-now)."""
    result = _experience("backend_java", 9, real_embedder)
    factors = {r.title: r.factor for r in result.roles}
    assert factors == {
        "Senior Java Developer": 1.0,  # Mar 2020 - now: 81 months
        "Freelance Backend Consultant": 1.0,  # inside it: adds nothing
        "Java Developer": 0.5,  # Jul 2017 - Feb 2020: 32 months x 0.5
    }
    assert result.relevant_months == 81 + 16
