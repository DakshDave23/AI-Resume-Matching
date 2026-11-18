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
    # Uvicorn's access log duplicates what we need at INFO; keep it at WARNING.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
