"""Shared FastAPI dependencies.

Models are loaded once by the lifespan hook and kept on `app.state`; routes get
them through these functions, so tests can swap in fakes.
"""

from fastapi import Depends, Request

from app.core.errors import AppError
from app.services.nlp.embedder import TextEncoder
from app.services.nlp.loader import ModelLoader, ModelNotReadyError


def get_model_loader(request: Request) -> ModelLoader:
    loader = request.app.state.model_loader
    if not isinstance(loader, ModelLoader):
        raise TypeError("app.state.model_loader is not set; create the app with create_app()")
    return loader


def get_embedder(loader: ModelLoader = Depends(get_model_loader)) -> TextEncoder:
    """The embedding model, or 503 while it is still loading (or failed to load)."""
    try:
        return loader.embedder()
    except ModelNotReadyError as exc:
        if exc.status == "loading":
            raise AppError(
                503,
                "The embedding model is still loading. Try again in a few seconds.",
                code="model_loading",
            ) from exc
        raise AppError(
            503,
            "The embedding model failed to load; see the server log.",
            code="model_unavailable",
        ) from exc
