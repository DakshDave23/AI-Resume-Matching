"""Step 27's "done when": points add up to the match % (real model, every sample x JD).

Also Candidate A's explanation against design doc §6.6.
"""

from functools import cache
from typing import Any

import pytest

from app.services.matching.explainer import MINUS, explain
from app.services.matching.inputs import candidate_data_from_parse, skill_vectors
from app.services.matching.scorer import MatchOutcome, score_candidate, scoring_job_from_parse
from app.services.nlp.embedder import Embedder
from app.services.nlp.vectors import embed_job, embed_resume
from app.services.parsing.chunker import chunk_resume
from app.services.parsing.jd_parser import parse_job
from app.services.parsing.resume_parser import parse_resume
from tests.samples import AS_OF, JDS, TEXT_RESUMES, jd, jd_text, resume_text, text_resume

pytestmark = pytest.mark.model


@cache
def _outcome(jd_key: str, persona: int, embedder: Embedder) -> MatchOutcome:
    job = parse_job(jd_text(jd(jd_key)))
    parsed = parse_resume(resume_text(text_resume(persona)), today=AS_OF, region="IN")
    chunks = chunk_resume(parsed.sections, parsed.work)
    vectors = skill_vectors(sorted({s.name for s in job.skills} | parsed.skills.names()), embedder)
    scoring_job = scoring_job_from_parse(
        job, embed_job(job.requirements, embedder), vectors, embedder
    )
    candidate = candidate_data_from_parse(
        parsed,
        chunks,
        embed_resume(chunks, parsed.work.roles, embedder),
        vectors,
        list(scoring_job.skills.skills),
    )
    return score_candidate(scoring_job, candidate, today=AS_OF, encoder=embedder)


PAIRS = [(j["id"], r["id"]) for j in JDS for r in TEXT_RESUMES]


@pytest.mark.parametrize(("jd_key", "persona"), PAIRS, ids=lambda v: str(v))
def test_points_add_up_to_the_match_percent(
    jd_key: str, persona: int, real_embedder: Embedder
) -> None:
    outcome = _outcome(jd_key, persona, real_embedder)
    result: dict[str, Any] = explain(outcome)
    parts = result["breakdown"]

    shown = round(outcome.score, 1)
    assert sum(p["earned"] for p in parts) == pytest.approx(shown)  # exactly, as displayed
    assert result["score"] == pytest.approx(shown)
    assert sum(p["available"] for p in parts) == pytest.approx(100.0)
    for part in parts:
        assert part["earned"] + part["lost"] == pytest.approx(part["available"])
        assert part["lost"] >= 0
    lost_on_skills = sum(
        -i["impact"] for i in result["items"] if i["type"].startswith("skill") and i["impact"] < 0
    )
    skill_part = next(p for p in parts if p["component"] == "skills")
    assert lost_on_skills == pytest.approx(
        skill_part["lost"], abs=0.05 * len(outcome.skills.matches)
    )


def test_candidate_a_explanation(real_embedder: Embedder) -> None:
    result = explain(_outcome("backend_java", 3, real_embedder))
    assert result["verdict"] == "strong"
    assert "Has 5 of 5 required skills" in result["summary"]
    assert {g["message"] for g in result["gaps"]} == {
        f'Microservices not listed, but inferred from the "Java Developer | Contoso Payments" '
        f"role ({MINUS}3.1 points).",
        f"PostgreSQL credited at half: related skill MySQL found ({MINUS}3.1 points).",
        f"Missing preferred skill AWS ({MINUS}3.1 points).",
        f"Kafka credited at half: related skill RabbitMQ found ({MINUS}1.5 points).",
    }  # §6.6: 3.1 + 3.1 + 3.1 + 1.5 = 10.8 lost on skills
    assert result["strengths"][0]["message"] == (
        "4.5 years of relevant experience meets the 4-year minimum."
    )
