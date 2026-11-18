"""Stand-ins for slow dependencies, shared by unit and integration tests."""

import hashlib
from collections.abc import Sequence

import numpy as np

from app.models.base import EMBEDDING_DIM
from app.services.nlp.embedder import Vectors, clean_texts


class FakeEncoder:
    """Deterministic bag-of-words vectors: texts sharing words get a higher cosine.

    No model, no torch: instant. Like the real one, it returns unit-length float32
    rows and rejects blank text.
    """

    model_name = "fake-bag-of-words"

    def __init__(self) -> None:
        self.calls: list[list[str]] = []  # every batch it was asked to encode

    def encode(self, texts: Sequence[str]) -> Vectors:
        cleaned = clean_texts(texts)
        self.calls.append(cleaned)
        vectors = np.zeros((len(cleaned), EMBEDDING_DIM), dtype=np.float32)
        for row, text in enumerate(cleaned):
            for word in text.lower().split():
                digest = hashlib.sha256(word.encode()).digest()
                vectors[row, int.from_bytes(digest[:4], "big") % EMBEDDING_DIM] += 1.0
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return (vectors / np.where(norms == 0, 1.0, norms)).astype(np.float32)
