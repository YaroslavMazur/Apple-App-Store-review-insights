from __future__ import annotations

import logging
import sys

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars
from structlog.types import Processor

from app.config import Settings

__all__ = ["bind_contextvars", "clear_contextvars", "configure_logging", "get_logger"]


def configure_logging(settings: Settings) -> None:
    """Configure structlog. JSON output in prod/test, human-readable in dev."""
    level = getattr(logging, settings.log_level)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: Processor = (
        structlog.dev.ConsoleRenderer(colors=True)
        if settings.env == "dev"
        else structlog.processors.JSONRenderer()
    )

    structlog.configure(
        processors=[*shared, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
