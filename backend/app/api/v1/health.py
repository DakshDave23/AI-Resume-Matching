from fastapi import APIRouter, Depends, Response, status

from app import __version__
from app.api.deps import get_model_loader
from app.core.config import Settings, get_settings
from app.core.database import DatabaseStatus, get_database_status
from app.schemas.health import HealthResponse
from app.services.nlp.loader import ModelLoader

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
    models: ModelLoader = Depends(get_model_loader),
) -> HealthResponse:
    checks = {
        "database": "ok" if db.reachable else "unavailable",
        "pgvector": db.pgvector_version or "missing",
        # 503 while loading: a load balancer or `docker compose --wait` holds traffic back.
        "embedding_model": "ok" if models.status == "ready" else models.status,
    }
    ready = db.reachable and db.pgvector_version is not None and models.status == "ready"

    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ok" if ready else "degraded",
        version=__version__,
        environment=settings.app_env,
        checks=checks,
    )
