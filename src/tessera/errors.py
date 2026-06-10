"""Centralized exception hierarchy for tessera.

All custom exceptions live here so callers can catch a single base type
(:class:`TesseraError`) or a specific failure mode. No module should define
its own ad-hoc exception types elsewhere.
"""

from __future__ import annotations


class TesseraError(Exception):
    """Base class for every error raised by tessera."""


class ConfigError(TesseraError):
    """Raised when configuration is missing, malformed, or internally inconsistent."""


class EdgarHTTPError(TesseraError):
    """Raised when an SEC EDGAR request fails terminally.

    Attributes:
        status_code: The HTTP status code of the failing response, if known.
        url: The request URL that failed, if known.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        url: str | None = None,
    ) -> None:
        """Initialize the error.

        Args:
            message: Human-readable description of the failure.
            status_code: HTTP status code of the failing response, if known.
            url: The request URL that failed, if known.
        """
        super().__init__(message)
        self.status_code = status_code
        self.url = url


class RateLimitError(TesseraError):
    """Raised when the self-imposed request rate limit cannot be satisfied."""


class NormalizationError(TesseraError):
    """Raised when a raw XBRL tag cannot be mapped to a standard concept."""


class CatalogError(TesseraError):
    """Raised when the Iceberg catalog cannot be built or accessed."""


class WarehouseError(TesseraError):
    """Raised when a warehouse (DuckDB/Snowflake) operation fails."""
