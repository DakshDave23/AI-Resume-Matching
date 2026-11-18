"""Turn a parsed resume or JD into the vectors stored in pgvector (design doc §5, §6.3).

- Resume: one vector per chunk, one per role (title + description, for role
  relevance in §6.4), and a whole-resume vector.
- JD: one vector per requirement sentence and a whole-JD vector.

The whole-document vector is the normalised mean of the document's chunk (or
requirement) vectors, as §6.3 defines it. Each document takes one batched model call.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from app.models.base import EMBEDDING_DIM
from app.services.nlp.embedder import TextEncoder, Vectors
from app.services.parsing.chunker import Chunk
from app.services.parsing.experience import Role
from app.services.parsing.jd_parser import JobRequirement

Vector = NDArray[np.float32]


def mean_vector(vectors: Vectors) -> Vector | None:
    """The normalised mean of unit vectors; None for no vectors (or ones that cancel out)."""
    if len(vectors) == 0:
        return None
    mean = vectors.mean(axis=0)
    norm = float(np.linalg.norm(mean))
    if norm < 1e-6:
        return None
    result: Vector = (mean / norm).astype(np.float32)
    return result


def role_text(role: Role) -> str | None:
    """Title + description: what the role was, and what was done in it."""
    parts = [part for part in (role.title, role.description) if part and part.strip()]
    return "\n".join(parts) if parts else None


@dataclass(frozen=True)
class ResumeVectors:
    chunks: Vectors  # row i belongs to chunk i
    roles: list[Vector | None]  # one per role; None for a role with neither title nor text
    document: Vector | None  # None when the resume has no chunks


@dataclass(frozen=True)
class JobVectors:
    requirements: Vectors  # row i belongs to requirement i
    document: Vector | None


def embed_resume(
    chunks: Sequence[Chunk], roles: Sequence[Role], encoder: TextEncoder
) -> ResumeVectors:
    role_texts = [role_text(role) for role in roles]
    texts = [c.text for c in chunks] + [t for t in role_texts if t is not None]
    vectors = encoder.encode(texts) if texts else np.zeros((0, EMBEDDING_DIM), np.float32)

    chunk_vectors = vectors[: len(chunks)]
    role_rows = iter(vectors[len(chunks) :])
    role_vectors = [next(role_rows) if text is not None else None for text in role_texts]
    return ResumeVectors(chunk_vectors, role_vectors, mean_vector(chunk_vectors))


def embed_job(requirements: Sequence[JobRequirement], encoder: TextEncoder) -> JobVectors:
    texts = [r.text for r in requirements]
    vectors = encoder.encode(texts) if texts else np.zeros((0, EMBEDDING_DIM), np.float32)
    return JobVectors(vectors, mean_vector(vectors))
