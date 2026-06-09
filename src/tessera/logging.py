"""Structured logging configuration built on structlog.

Provides a single :func:`configure_logging` entry point (console renderer for the
local profile, JSON for cloud), a :func:`get_logger` factory, and
:func:`bind_run_context` for attaching run-scoped context (``run_id``, ``cik``,
``concept``) to every subsequent log line. No module should use ``print``.
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, cast

import structlog

if TYPE_CHECKING:
    from tessera.config import Settings

_CONFIGURED = False


def configure_logging(settings: Settings) -> None:
    """Configure structlog and the stdlib logging backend for the given profile.

    Safe to call more than once; repeated calls reconfigure idempotently. Uses a
    human-readable console renderer locally and machine-parsable JSON in the cloud,
    with ISO-8601 timestamps and the active ``profile`` bound to every log line.

    Args:
        settings: The resolved application settings.
    """
    global _CONFIGURED

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if settings.is_cloud
        else structlog.dev.ConsoleRenderer()
    )

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO, force=True)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(profile=settings.profile)
    _CONFIGURED = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound logger for the given name.

    Args:
        name: Logger name, conventionally the module's ``__name__``.

    Returns:
        A structlog bound logger.
    """
    return cast("structlog.stdlib.BoundLogger", structlog.get_logger(name))


def bind_run_context(
    *,
    run_id: str,
    cik: str | None = None,
    concept: str | None = None,
) -> structlog.stdlib.BoundLogger:
    """Return a logger with run-scoped context bound to it.

    Args:
        run_id: Identifier for the current pipeline/ingest run.
        cik: Optional zero-padded company CIK to bind.
        concept: Optional standard concept name to bind.

    Returns:
        A bound logger carrying the supplied context on every emitted event.
    """
    context: dict[str, str] = {"run_id": run_id}
    if cik is not None:
        context["cik"] = cik
    if concept is not None:
        context["concept"] = concept
    logger = get_logger("tessera.run")
    return logger.bind(**context)
