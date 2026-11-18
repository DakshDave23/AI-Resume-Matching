from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    environment: str
    # Per-dependency readiness, e.g.
    # {"database": "ok", "pgvector": "0.8.0", "embedding_model": "ok" | "loading" | "failed"}.
    checks: dict[str, str] = Field(default_factory=dict)
