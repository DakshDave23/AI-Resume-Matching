from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    environment: str
    # Per-dependency readiness, e.g. {"database": "ok", "embedding_model": "loading"}.
    # Filled in as dependencies are added (database in step 3, model in step 17).
    checks: dict[str, str] = Field(default_factory=dict)
