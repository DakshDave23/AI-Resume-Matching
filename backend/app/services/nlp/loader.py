"""Load the NLP models once, off the request path (design doc §8 and §9).

The lifespan hook starts a `ModelLoader`, which loads the spaCy skill extractor
and the embedding model in a background thread. The API starts serving at once:
/health answers 503 with "loading" until both are ready, and routes that need
the embedder answer 503 instead of hanging for twenty seconds.
"""

import logging
import threading
import time
from collections.abc import Callable
from typing import Literal

from app.services.nlp.embedder import TextEncoder

logger = logging.getLogger(__name__)

ModelStatus = Literal["loading", "ready", "failed"]


class ModelNotReadyError(RuntimeError):
    def __init__(self, status: ModelStatus) -> None:
        super().__init__(f"the embedding model is {status}")
        self.status = status


class ModelLoader:
    """Runs `load` once in a daemon thread and keeps what it returns."""

    def __init__(self, load: Callable[[], TextEncoder]) -> None:
        self._load = load
        self._done = threading.Event()
        self._start_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._encoder: TextEncoder | None = None
        self.error: str | None = None

    def start(self) -> None:
        """Begin loading. Calling it again does nothing: the model loads once."""
        with self._start_lock:
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name="model-loader", daemon=True)
                self._thread.start()

    def _run(self) -> None:
        started = time.perf_counter()
        try:
            encoder = self._load()
        except Exception as exc:  # report it on /health; the API keeps serving
            logger.exception("Loading the NLP models failed")
            self.error = f"{type(exc).__name__}: {exc}"
        else:
            self._encoder = encoder
            seconds = time.perf_counter() - started
            logger.info("NLP models ready in %.1f s (%s)", seconds, encoder.model_name)
        finally:
            self._done.set()

    @property
    def status(self) -> ModelStatus:
        if not self._done.is_set():
            return "loading"
        return "ready" if self._encoder is not None else "failed"

    def wait(self, timeout: float | None = None) -> bool:
        """Block until loading finishes (scripts and tests); True when it has."""
        return self._done.wait(timeout)

    def embedder(self) -> TextEncoder:
        if self._encoder is None:
            raise ModelNotReadyError(self.status)
        return self._encoder
