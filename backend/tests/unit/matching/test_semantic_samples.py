"""Step 23's "done when": irrelevant samples land near 0 (real model, real samples).

Also: in every JD, each "strong" sample scores above every "weak" one.
"""

from functools import cache

import pytest

from app.services.matching.inputs import requirements_from_parse
from app.services.matching.semantic import Coverage, SemanticScore, semantic_score
from app.services.matching.skills import Passage
from app.services.nlp.embedder import Embedder
from app.services.nlp.vectors import embed_job, embed_resume
from app.services.parsing.chunker import chunk_resume
from app.services.parsing.jd_parser import parse_job
from app.services.parsing.resume_parser import parse_resume
from tests.samples import AS_OF, JDS, TEXT_RESUMES, jd, jd_text, resume_text, text_resume

pytestmark = pytest.mark.model


@cache
def _semantic(jd_key: str, persona: int, embedder: Embedder) -> SemanticScore:
    job = parse_job(jd_text(jd(jd_key)))
    job_vectors = embed_job(job.requirements, embedder)
    parsed = parse_resume(resume_text(text_resume(persona)), today=AS_OF, region="IN")
    chunks = chunk_resume(parsed.sections, parsed.work)
    vectors = embed_resume(chunks, parsed.work.roles, embedder)
    passages = [Passage(c.section, c.text, v) for c, v in zip(chunks, vectors.chunks, strict=True)]
    result = semantic_score(
        requirements_from_parse(job, job_vectors.requirements),
        passages,
        job_vector=job_vectors.document,
        resume_vector=vectors.document,
    )
    assert result is not None
    return result


@pytest.mark.parametrize(
    "persona", [13, 12, 7], ids=["accountant", "data-scientist", "keyword-stuffer"]
)
def test_irrelevant_samples_land_near_zero_for_the_java_jd(
    persona: int, real_embedder: Embedder
) -> None:
    assert _semantic("backend_java", persona, real_embedder).score <= 0.05


def test_the_accountant_is_near_zero_for_every_jd(real_embedder: Embedder) -> None:
    for job in JDS:
        assert _semantic(job["id"], 13, real_embedder).score == 0.0, job["id"]


@pytest.mark.parametrize("jd_key", [j["id"] for j in JDS])
def test_strong_samples_score_above_weak_ones(jd_key: str, real_embedder: Embedder) -> None:
    def scores(tier: str) -> list[float]:
        return [
            _semantic(jd_key, r["id"], real_embedder).score
            for r in TEXT_RESUMES
            if r["expected_tier"][jd_key] == tier
        ]

    assert min(scores("strong")) > max(scores("weak")) + 0.3


def test_candidate_a_requirement_table(real_embedder: Embedder) -> None:
    table = {m.text: m.status for m in _semantic("backend_java", 3, real_embedder).matches}
    status = {text.split()[0] + " " + text.split()[1]: s for text, s in table.items()}
    assert status["Design and"] == Coverage.COVERED  # "...scalable backend services..."
    assert status["Exposure to"] == Coverage.NOT_COVERED  # AWS
    assert status["Familiarity with"] == Coverage.NOT_COVERED  # Kafka
    assert not any("years" in text or "degree" in text for text in table)  # other components
