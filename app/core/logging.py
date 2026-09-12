"""Application logging.

Log level comes from Settings. Do not log secrets, request bodies,
or sensitive environment values.
"""

from __future__ import annotations

import logging
import sys
import time

from app.core.config import settings


class _UTCFormatter(logging.Formatter):
    converter = time.gmtime


def setup_logging() -> None:
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    app_logger = logging.getLogger("app")
    app_logger.setLevel(level)

    if not app_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            _UTCFormatter(
                fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%SZ",
            )
        )
        app_logger.addHandler(handler)
        app_logger.propagate = False

    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
