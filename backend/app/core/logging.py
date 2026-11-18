"""Process-wide logging setup."""

import logging
import sys

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        stream=sys.stdout,
        force=True,  # replace handlers so repeated app creation (tests) doesn't duplicate output
    )
    # Uvicorn's access log duplicates what we need at INFO; keep it at WARNING. The
    # Hugging Face libraries log every HTTP request made while fetching the model.
    for noisy in ("uvicorn.access", "httpx", "httpx2", "huggingface_hub", "sentence_transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
