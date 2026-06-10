"""Rate-limited, retrying HTTP client for the SEC EDGAR APIs.

:class:`EdgarClient` is the only place the project talks to SEC over the network.
It injects a descriptive ``User-Agent``, enforces a self-imposed request rate via a
thread-safe minimum-interval gate, retries transient failures (429/403/5xx and
transport errors) with exponential backoff, and returns typed pydantic models.
Retries live here and nowhere else.
"""

from __future__ import annotations

import time
from threading import Lock
from typing import TYPE_CHECKING, Any, Self

import httpx
from tenacity import (
    RetryError,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from tessera.errors import EdgarHTTPError
from tessera.ingestion.models import (
    CompanyConcept,
    CompanyFacts,
    FrameResponse,
    Submissions,
    TickerMapEntry,
)
from tessera.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

    from structlog.stdlib import BoundLogger

    from tessera.config import Settings

DATA_BASE = "https://data.sec.gov"
WWW_BASE = "https://www.sec.gov"
TICKER_MAP_URL = f"{WWW_BASE}/files/company_tickers.json"

# Status codes worth retrying: SEC throttling (429), occasional 403s, and 5xx.
RETRYABLE_STATUS = frozenset({403, 429, 500, 502, 503, 504})


class _RetryableHTTPError(Exception):
    """Internal signal that a response carried a retryable status code."""

    def __init__(self, status_code: int, url: str) -> None:
        super().__init__(f"retryable status {status_code} for {url}")
        self.status_code = status_code
        self.url = url


class _RateLimiter:
    """Thread-safe minimum-interval gate enforcing at most N requests/second."""

    def __init__(
        self,
        rate_per_sec: float,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Initialize the limiter.

        Args:
            rate_per_sec: Maximum sustained requests per second (<= 0 disables gating).
            monotonic: Clock source returning seconds; injectable for tests.
            sleep: Sleep function; injectable for tests.
        """
        self._min_interval = 1.0 / rate_per_sec if rate_per_sec > 0 else 0.0
        self._monotonic = monotonic
        self._sleep = sleep
        self._lock = Lock()
        self._next_allowed = 0.0

    def acquire(self) -> None:
        """Block until the next request is permitted under the rate limit."""
        with self._lock:
            now = self._monotonic()
            wait = self._next_allowed - now
            if wait > 0:
                self._sleep(wait)
                now = self._monotonic()
            self._next_allowed = now + self._min_interval


class EdgarClient:
    """Typed, rate-limited client for the SEC EDGAR REST endpoints."""

    def __init__(
        self,
        settings: Settings,
        *,
        max_attempts: int = 5,
        backoff: float = 0.5,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the client.

        Args:
            settings: Application settings supplying the User-Agent and rate limit.
            max_attempts: Maximum number of attempts per request before failing.
            backoff: Exponential-backoff multiplier (seconds); use 0 to disable waits.
            timeout: Per-request timeout in seconds.
        """
        self._settings = settings
        self._log = get_logger("tessera.ingestion.edgar_client")
        self._rate_limiter = _RateLimiter(settings.request_rate_limit)
        self._max_attempts = max_attempts
        self._backoff = backoff
        self._client = httpx.Client(
            headers={
                "User-Agent": settings.sec_user_agent,
                "Accept-Encoding": "gzip, deflate",
            },
            timeout=httpx.Timeout(timeout),
        )

    @staticmethod
    def _format_cik(cik: int | str) -> str:
        """Return the CIK zero-padded to ten digits.

        Args:
            cik: A CIK as an integer or numeric string.

        Returns:
            The 10-digit zero-padded CIK string.
        """
        return f"{int(cik):010d}"

    def _attempt(self, url: str, log: BoundLogger) -> Any:
        """Perform one rate-limited GET and classify the response.

        Raises:
            _RetryableHTTPError: When the status code is retryable.
            EdgarHTTPError: When the status code is a non-retryable client error.
        """
        self._rate_limiter.acquire()
        log.debug("edgar_request", url=url)
        response = self._client.get(url)
        status = response.status_code
        if status in RETRYABLE_STATUS:
            log.warning("edgar_retryable_status", url=url, status_code=status)
            raise _RetryableHTTPError(status, url)
        if status >= 400:
            raise EdgarHTTPError(f"SEC request failed [{status}]", status_code=status, url=url)
        return response.json()

    def _get_json(self, url: str, log: BoundLogger) -> Any:
        """GET ``url`` with retries, returning parsed JSON.

        Args:
            url: The absolute request URL.
            log: A bound logger carrying request context.

        Returns:
            The decoded JSON payload.

        Raises:
            EdgarHTTPError: When the request fails terminally after all retries.
        """
        retryer = Retrying(
            retry=retry_if_exception_type((_RetryableHTTPError, httpx.TransportError)),
            wait=wait_exponential(multiplier=self._backoff, max=10.0),
            stop=stop_after_attempt(self._max_attempts),
            reraise=False,
        )
        try:
            return retryer(self._attempt, url, log)
        except RetryError as exc:
            last = exc.last_attempt.exception()
            status = getattr(last, "status_code", None)
            log.error("edgar_request_failed", url=url, status_code=status)
            raise EdgarHTTPError(
                f"SEC request failed after {self._max_attempts} attempts: {url}",
                status_code=status,
                url=url,
            ) from last

    def get_company_facts(self, cik: int | str) -> CompanyFacts:
        """Fetch all XBRL facts for one issuer.

        Args:
            cik: The issuer's CIK (any width; zero-padded internally).

        Returns:
            The parsed :class:`CompanyFacts` payload.
        """
        padded = self._format_cik(cik)
        log = self._log.bind(cik=padded)
        url = f"{DATA_BASE}/api/xbrl/companyfacts/CIK{padded}.json"
        return CompanyFacts.model_validate(self._get_json(url, log))

    def get_company_concept(
        self, cik: int | str, tag: str, taxonomy: str = "us-gaap"
    ) -> CompanyConcept:
        """Fetch one tag's full history for one issuer.

        Args:
            cik: The issuer's CIK.
            tag: The XBRL tag (e.g. ``Revenues``).
            taxonomy: The taxonomy namespace (default ``us-gaap``).

        Returns:
            The parsed :class:`CompanyConcept` payload.
        """
        padded = self._format_cik(cik)
        log = self._log.bind(cik=padded, concept=tag)
        url = f"{DATA_BASE}/api/xbrl/companyconcept/CIK{padded}/{taxonomy}/{tag}.json"
        return CompanyConcept.model_validate(self._get_json(url, log))

    def get_frame(
        self, tag: str, year: int, unit: str = "USD", taxonomy: str = "us-gaap"
    ) -> FrameResponse:
        """Fetch one tag across all issuers for one calendar-year frame.

        Args:
            tag: The XBRL tag (e.g. ``Revenues``).
            year: The calendar year of the frame.
            unit: The unit of measure (default ``USD``).
            taxonomy: The taxonomy namespace (default ``us-gaap``).

        Returns:
            The parsed :class:`FrameResponse` payload.
        """
        log = self._log.bind(concept=tag)
        url = f"{DATA_BASE}/api/xbrl/frames/{taxonomy}/{tag}/{unit}/CY{year}.json"
        return FrameResponse.model_validate(self._get_json(url, log))

    def get_submissions(self, cik: int | str) -> Submissions:
        """Fetch filing history and metadata for one issuer.

        Args:
            cik: The issuer's CIK.

        Returns:
            The parsed :class:`Submissions` payload.
        """
        padded = self._format_cik(cik)
        log = self._log.bind(cik=padded)
        url = f"{DATA_BASE}/submissions/CIK{padded}.json"
        return Submissions.model_validate(self._get_json(url, log))

    def get_ticker_map(self) -> list[TickerMapEntry]:
        """Fetch the ticker -> CIK map.

        Returns:
            One :class:`TickerMapEntry` per row of ``company_tickers.json``.
        """
        data = self._get_json(TICKER_MAP_URL, self._log)
        return [TickerMapEntry.model_validate(entry) for entry in data.values()]

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> Self:
        """Enter the runtime context, returning this client."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Exit the runtime context, closing the client."""
        self.close()
