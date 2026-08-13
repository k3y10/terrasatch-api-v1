"""Structured logging configuration."""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(*, level: str, json_output: bool = True) -> None:
    """Configure stdlib and structlog to emit request-safe structured records."""

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level, force=True)
    renderer: structlog.types.Processor
    if json_output:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level, logging.INFO)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )