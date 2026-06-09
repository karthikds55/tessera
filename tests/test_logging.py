"""Tests for tessera.logging: configuration idempotency and bound loggers."""

from __future__ import annotations

import structlog

from tessera.config import Settings
from tessera.logging import bind_run_context, configure_logging, get_logger


def test_configure_logging_is_idempotent() -> None:
    settings = Settings(profile="local")
    configure_logging(settings)
    configure_logging(settings)  # second call must not raise

    assert structlog.is_configured()


def test_get_logger_returns_usable_logger() -> None:
    configure_logging(Settings(profile="local"))

    logger = get_logger("tessera.test")

    assert hasattr(logger, "info")
    logger.info("hello", extra_key="value")  # should not raise


def test_bind_run_context_binds_fields() -> None:
    configure_logging(Settings(profile="cloud"))

    logger = bind_run_context(run_id="run-123", cik="0000320193", concept="revenue")

    assert hasattr(logger, "info")
    logger.info("bound event")  # should not raise
