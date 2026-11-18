from fastapi import APIRouter, Depends, Response, status

from app import __version__
from app.core.config import Settings, get_settings
from app.core.database import DatabaseStatus, get_database_status
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness and readiness",
    responses={503: {"model": HealthResponse, "description": "A dependency is not ready"}},
)
def health(
    response: Response,
    settings: Settings = Depends(get_settings),
    db: DatabaseStatus = Depends(get_database_status),
) -> HealthResponse:
    checks = {
        "database": "ok" if db.reachable else "unavailable",
        "pgvector": db.pgvector_version or "missing",
    }
    # Step 17 adds: "embedding_model": "ok" | "loading"
    ready = db.reachable and db.pgvector_version is not None

    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ok" if ready else "degraded",
        version=__version__,
        environment=settings.app_env,
        checks=checks,
    )
