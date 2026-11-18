"""The real embedding model: loaded once for this module (a few seconds, cached on disk).

Skip with `pytest -m "not model"` for a quick run.
"""

import sys
import types

import numpy as np
import pytest

from app.core.config import get_settings
from app.models.base import EMBEDDING_DIM
from app.services.nlp.embedder import Embedder, EmbeddingError, encode_one

pytestmark = pytest.mark.model


@pytest.fixture(scope="module")
def embedder() -> Embedder:
    return Embedder(get_settings().embedding_model)


def cosine(embedder: Embedder, a: str, b: str) -> float:
    return float(encode_one(embedder, a) @ encode_one(embedder, b))


def test_vectors_are_384_float32_and_unit_length(embedder: Embedder) -> None:
    vectors = embedder.encode(["Built REST APIs in Java", "Led a team of five"])
    assert vectors.shape == (2, EMBEDDING_DIM)
    assert vectors.dtype == np.float32
    np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-5)


def test_a_batch_matches_one_at_a_time_in_order(embedder: Embedder) -> None:
    texts = ["Kafka consumers", "Spring Boot services", "Tuned PostgreSQL queries"]
    batch = embedder.encode(texts)
    for row, text in enumerate(texts):
        np.testing.assert_allclose(batch[row], encode_one(embedder, text), atol=1e-5)


def test_the_same_text_always_gets_the_same_vector(embedder: Embedder) -> None:
    first = encode_one(embedder, "Designed microservices")
    np.testing.assert_allclose(encode_one(embedder, "Designed microservices"), first, atol=1e-6)


def test_whitespace_does_not_change_the_vector(embedder: Embedder) -> None:
    np.testing.assert_allclose(
        encode_one(embedder, "  Designed\n microservices\t"),
        encode_one(embedder, "Designed microservices"),
        atol=1e-6,
    )


def test_meaning_not_just_words(embedder: Embedder) -> None:
    """The reason for embeddings (design doc §2): different words, same meaning."""
    related = cosine(embedder, "built RESTful services", "REST API development")
    unrelated = cosine(embedder, "built RESTful services", "baked sourdough bread")
    assert related > 0.5 > unrelated


def test_empty_input_gives_an_empty_matrix(embedder: Embedder) -> None:
    assert embedder.encode([]).shape == (0, EMBEDDING_DIM)


def test_blank_text_is_refused(embedder: Embedder) -> None:
    with pytest.raises(ValueError, match=r"blank text \(positions \[1\]\)"):
        embedder.encode(["Java", "   "])


def test_long_text_is_truncated_not_rejected(embedder: Embedder) -> None:
    assert embedder.max_tokens == 256
    assert embedder.encode(["word " * 2000]).shape == (1, EMBEDDING_DIM)


def test_a_model_with_the_wrong_vector_size_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    class WideModel:
        def __init__(self, name: str, **kwargs: object) -> None:
            pass

        def get_embedding_dimension(self) -> int:
            return 768

    fake = types.ModuleType("sentence_transformers")
    fake.SentenceTransformer = WideModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake)

    with pytest.raises(EmbeddingError, match="768-dimensional"):
        Embedder("some/mpnet-model")
