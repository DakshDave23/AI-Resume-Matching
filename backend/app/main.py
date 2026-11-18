"""FastAPI application factory.

Run locally:  uvicorn app.main:app --reload   (from the backend/ folder)
Swagger UI:   http://localhost:8000/docs
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import get_engine
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.services.nlp.embedder import Embedder, TextEncoder
from app.services.nlp.loader import ModelLoader
from app.services.parsing.skills import get_skill_extractor

logger = logging.getLogger(__name__)


def load_models() -> TextEncoder:
    """Everything slow to load, in one go: spaCy's skill matcher, then the embedding model."""
    get_skill_extractor()  # cached for the life of the process
    settings = get_settings()
    return Embedder(settings.embedding_model, batch_size=settings.embedding_batch_size)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info("Starting %s v%s (env=%s)", settings.app_name, __version__, settings.app_env)
    # Load in the background: the API serves at once, and /health says 503 until ready.
    app.state.model_loader.start()
    yield
    get_engine().dispose()  # close pooled DB connections cleanly
    logger.info("Shutting down")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Rank resumes against a job description with explainable scores.",
        lifespan=lifespan,
    )
    # Started by the lifespan hook. Tests replace it with a loader that returns a fake.
    app.state.model_loader = ModelLoader(load_models)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,  # only the frontend origin(s), never "*"
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
