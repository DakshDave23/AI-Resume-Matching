"""Step 22's "done when": Candidate A's skill table matches design doc §6.6.

Real model, real parsers, real samples. Also pins every related and contextual
hit across all 3 JDs x 14 samples, so a threshold or model change that adds a
false match (Java <- Python, Docker <- Jenkins) fails here.
"""

from functools import cache

import pytest

from app.services.matching.inputs import (
    candidate_from_parse,
    job_skills_from_parse,
    skill_vectors,
)
from app.services.matching.skills import SkillScore, Tier, match_skills, prepare_job
from app.services.nlp.embedder import Embedder
from app.services.parsing.chunker import chunk_resume
from app.services.parsing.jd_parser import parse_job
from app.services.parsing.resume_parser import parse_resume
from tests.samples import AS_OF, JDS, TEXT_RESUMES, jd, jd_text, resume_text, text_resume

pytestmark = pytest.mark.model


@cache
def _score(jd_key: str, persona: int, embedder: Embedder) -> SkillScore:
    job = parse_job(jd_text(jd(jd_key)))
    parsed = parse_resume(resume_text(text_resume(persona)), today=AS_OF, region="IN")
    chunks = chunk_resume(parsed.sections, parsed.work)
    names = sorted({s.name for s in job.skills} | parsed.skills.names())
    vectors = skill_vectors(names, embedder)
    job_skills = job_skills_from_parse(job, vectors)
    candidate, passages = candidate_from_parse(
        parsed, chunks, embedder.encode([c.text for c in chunks]), vectors, job_skills
    )
    return match_skills(prepare_job(job_skills, embedder), candidate, passages)


def test_candidate_a_matches_the_worked_example(real_embedder: Embedder) -> None:
    result = _score("backend_java", 3, real_embedder)
    table = {m.name: (m.requirement_type.value, m.weight, m.tier, m.credit) for m in result.matches}

    assert table == {
        "Java": ("required", 1.0, Tier.EXACT, 1.0),
        "Spring Boot": ("required", 1.0, Tier.EXACT, 1.0),
        "PostgreSQL": ("required", 1.0, Tier.RELATED, 0.5),
        "REST APIs": ("required", 1.0, Tier.ALIAS, 1.0),
        "Microservices": ("required", 1.0, Tier.CONTEXTUAL, 0.5),
        "Docker": ("preferred", 0.5, Tier.EXACT, 1.0),
        "Kafka": ("preferred", 0.5, Tier.RELATED, 0.5),
        "AWS": ("preferred", 0.5, Tier.MISSING, 0.0),
    }
    by_name = {m.name: m for m in result.matches}
    assert by_name["PostgreSQL"].matched_skill == "MySQL"
    assert by_name["Kafka"].matched_skill == "RabbitMQ"
    assert "Split a monolith into 8 independently deployed services" in (
        by_name["Microservices"].evidence or ""
    )
    assert sum(m.weight for m in result.matches) == 6.5
    assert sum(m.weighted_credit for m in result.matches) == 4.75
    assert result.score == pytest.approx(0.731, abs=5e-4)  # 4.75 / 6.5
    assert (result.required_matched, result.required_total) == (5, 5)


# (jd, persona) -> {skill: (tier, the resume skill it came from)}; every pair not listed has none.
INDIRECT = {
    ("backend_java", 3): {
        "Microservices": (Tier.CONTEXTUAL, None),
        "PostgreSQL": (Tier.RELATED, "MySQL"),
        "Kafka": (Tier.RELATED, "RabbitMQ"),
    },
    ("backend_java", 10): {
        "Spring Boot": (Tier.RELATED, "Spring"),
        "PostgreSQL": (Tier.RELATED, "MySQL"),
    },
    ("backend_java", 14): {"PostgreSQL": (Tier.RELATED, "MySQL")},
    ("data_scientist", 7): {
        "Statistics": (Tier.RELATED, "Machine Learning"),
        "Deep Learning": (Tier.RELATED, "Machine Learning"),
        "PyTorch": (Tier.RELATED, "TensorFlow"),
    },
    ("data_scientist", 12): {
        "Deep Learning": (Tier.RELATED, "Machine Learning"),
        "PyTorch": (Tier.RELATED, "TensorFlow"),
    },
}


@pytest.mark.parametrize("jd_key", [j["id"] for j in JDS])
def test_only_the_expected_indirect_matches_fire(jd_key: str, real_embedder: Embedder) -> None:
    for resume in TEXT_RESUMES:
        result = _score(jd_key, resume["id"], real_embedder)
        indirect = {
            m.name: (m.tier, m.matched_skill)
            for m in result.matches
            if m.tier in (Tier.RELATED, Tier.CONTEXTUAL)
        }
        assert indirect == INDIRECT.get((jd_key, resume["id"]), {}), resume["file"]
