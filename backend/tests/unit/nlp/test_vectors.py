import numpy as np

from app.models.enums import RequirementCategory, RequirementType
from app.services.nlp.vectors import embed_job, embed_resume, mean_vector, role_text
from app.services.parsing.chunker import Chunk
from app.services.parsing.experience import Role
from app.services.parsing.jd_parser import JobRequirement
from tests.fakes import FakeEncoder


def role(title: str | None, description: str = "") -> Role:
    return Role(title, None, None, None, description, is_internship=False)


def test_mean_vector_is_unit_length_and_points_between_its_inputs() -> None:
    vectors = np.eye(3, dtype=np.float32)[:2]  # two orthogonal unit vectors
    mean = mean_vector(vectors)
    assert mean is not None
    np.testing.assert_allclose(mean, [2**-0.5, 2**-0.5, 0], atol=1e-6)
    assert mean.dtype == np.float32


def test_mean_vector_of_nothing_is_none() -> None:
    assert mean_vector(np.zeros((0, 384), dtype=np.float32)) is None
    assert mean_vector(np.array([[1, 0], [-1, 0]], dtype=np.float32)) is None  # they cancel


def test_role_text_is_title_then_description() -> None:
    assert role_text(role("Java Developer", "- Built APIs.")) == "Java Developer\n- Built APIs."
    assert role_text(role(None, "- Built APIs.")) == "- Built APIs."
    assert role_text(role(None, "  ")) is None


def test_a_resume_takes_one_model_call() -> None:
    encoder = FakeEncoder()
    chunks = [Chunk("summary", "Java developer."), Chunk("experience", "Dev | Acme\n- Built APIs.")]
    roles = [role("Dev", "- Built APIs."), role(None), role("Tester")]

    result = embed_resume(chunks, roles, encoder)

    assert encoder.calls == [
        ["Java developer.", "Dev | Acme - Built APIs.", "Dev - Built APIs.", "Tester"]
    ]
    assert result.chunks.shape == (2, 384)
    assert [v is None for v in result.roles] == [False, True, False]
    tester, expected_document = result.roles[2], mean_vector(result.chunks)
    assert tester is not None and np.allclose(tester, encoder.encode(["Tester"])[0])
    assert result.document is not None and expected_document is not None
    assert np.allclose(result.document, expected_document)


def test_a_resume_with_nothing_to_embed_makes_no_call() -> None:
    encoder = FakeEncoder()
    result = embed_resume([], [], encoder)
    assert encoder.calls == []
    assert (result.chunks.shape, result.roles, result.document) == ((0, 384), [], None)


def test_a_job_embeds_every_requirement_in_one_call() -> None:
    encoder = FakeEncoder()
    required, preferred = RequirementType.REQUIRED, RequirementType.PREFERRED
    requirements = [
        JobRequirement("4+ years of Java.", RequirementCategory.EXPERIENCE, required),
        JobRequirement("Docker is a plus.", RequirementCategory.SKILL, preferred),
    ]
    result = embed_job(requirements, encoder)
    assert encoder.calls == [["4+ years of Java.", "Docker is a plus."]]
    assert result.requirements.shape == (2, 384)
    assert result.document is not None
