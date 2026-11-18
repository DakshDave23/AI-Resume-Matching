from fastapi import APIRouter, Depends

from app import __version__
from app.core.config import Settings, get_settings
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness and readiness")
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    # Returns 503 once there are dependencies that can be "not ready"
    # (database: step 3, embedding model: step 17).
    return HealthResponse(status="ok", version=__version__, environment=settings.app_env)
