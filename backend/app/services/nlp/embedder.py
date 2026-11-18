"""Sentence embeddings (design doc §2 and §5).

`Embedder` wraps one sentence-transformers model:

- the model name comes from settings (EMBEDDING_MODEL) and runs on the CPU;
- every vector is L2-normalised, so a dot product is the cosine similarity;
- texts are encoded in batches: one call per resume, not one per sentence;
- inference has no randomness, so the same text always gets the same vector.

sentence-transformers (and torch) are imported only when a model is loaded, so
importing the app, or running the unit tests, stays fast.
"""

import os
import threading
from collections.abc import Sequence
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from app.models.base import EMBEDDING_DIM

Vectors = NDArray[np.float32]  # shape (n, EMBEDDING_DIM), one row per text

DEFAULT_BATCH_SIZE = 32


class EmbeddingError(RuntimeError):
    """The model can't be used with this app (for example, the wrong vector size)."""


class TextEncoder(Protocol):
    """What the rest of the app needs from an embedding model. Tests use a fake."""

    @property
    def model_name(self) -> str: ...

    def encode(self, texts: Sequence[str]) -> Vectors: ...


def clean_texts(texts: Sequence[str]) -> list[str]:
    """Collapse whitespace; refuse blank texts, whose vector would mean nothing."""
    cleaned = [" ".join(text.split()) for text in texts]
    if blank := [i for i, text in enumerate(cleaned) if not text]:
        raise ValueError(f"cannot embed blank text (positions {blank})")
    return cleaned


def _quiet_hugging_face() -> None:
    # Download progress bars and the Windows symlink warning only clutter the API log.
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")


class Embedder:
    """A loaded sentence-transformers model. Loading takes seconds: do it once."""

    def __init__(self, model_name: str, *, batch_size: int = DEFAULT_BATCH_SIZE) -> None:
        _quiet_hugging_face()
        from sentence_transformers import SentenceTransformer  # slow: imports torch

        try:  # the cached copy first: no network call on every start, and it works offline
            model = SentenceTransformer(model_name, device="cpu", local_files_only=True)
        except OSError:  # not downloaded yet (about 90 MB, once)
            model = SentenceTransformer(model_name, device="cpu")
        dimension = model.get_embedding_dimension()
        if dimension != EMBEDDING_DIM:
            raise EmbeddingError(
                f"{model_name} makes {dimension}-dimensional vectors, but the database "
                f"stores {EMBEDDING_DIM}. Pick a {EMBEDDING_DIM}-dimensional model."
            )
        self._model = model
        self._name = model_name
        self._batch_size = batch_size
        # Hugging Face's fast tokenizers fail ("Already borrowed") when two threads use
        # one at once, and parallel calls wouldn't be faster on a CPU anyway.
        self._lock = threading.Lock()

    @property
    def model_name(self) -> str:
        return self._name

    @property
    def max_tokens(self) -> int:
        """Longer input is cut off: about 200 words for all-MiniLM-L6-v2."""
        return int(self._model.max_seq_length or 0)

    def encode(self, texts: Sequence[str]) -> Vectors:
        """Unit-length float32 vectors, one row per text, in the same order."""
        if not texts:
            return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
        cleaned = clean_texts(texts)
        with self._lock:
            vectors = self._model.encode(
                cleaned,
                batch_size=self._batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        return np.asarray(vectors, dtype=np.float32)


def encode_one(encoder: TextEncoder, text: str) -> NDArray[np.float32]:
    vectors: Vectors = encoder.encode([text])
    row: NDArray[np.float32] = vectors[0]
    return row
