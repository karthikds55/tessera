"""Tests for EdgarClient: parsing, retry, rate limiting, headers, CIK formatting.

All network calls are mocked with respx; no live SEC requests are made.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest
import respx

from tessera.config import Settings
from tessera.errors import EdgarHTTPError
from tessera.ingestion.edgar_client import EdgarClient, _RateLimiter

if TYPE_CHECKING:
    from typing import Any

FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"


def _fast_settings() -> Settings:
    """Settings with a high rate limit so tests do not sleep on the rate gate."""
    return Settings(
        profile="local",
        sec_user_agent="Tessera Test test@example.com",
        request_rate_limit=1000.0,
    )


def test_format_cik_zero_pads() -> None:
    assert EdgarClient._format_cik(320193) == "0000320193"
    assert EdgarClient._format_cik("320193") == "0000320193"


def test_get_company_facts_parses(companyfacts_payload: Any) -> None:
    with respx.mock() as router:
        router.get(FACTS_URL).mock(return_value=httpx.Response(200, json=companyfacts_payload))
        with EdgarClient(_fast_settings(), backoff=0.0) as client:
            facts = client.get_company_facts(320193)

    assert facts.cik == 320193
    assert facts.entity_name == "Apple Inc."


def test_retry_on_429_then_success(companyfacts_payload: Any) -> None:
    with respx.mock() as router:
        route = router.get(FACTS_URL).mock(
            side_effect=[
                httpx.Response(429),
                httpx.Response(200, json=companyfacts_payload),
            ]
        )
        with EdgarClient(_fast_settings(), max_attempts=3, backoff=0.0) as client:
            facts = client.get_company_facts(320193)

    assert facts.cik == 320193
    assert route.call_count == 2


def test_terminal_5xx_raises_after_retries() -> None:
    with respx.mock() as router:
        route = router.get(FACTS_URL).mock(return_value=httpx.Response(503))
        with EdgarClient(_fast_settings(), max_attempts=3, backoff=0.0) as client:  # noqa: SIM117
            with pytest.raises(EdgarHTTPError) as exc_info:
                client.get_company_facts(320193)

    assert exc_info.value.status_code == 503
    assert route.call_count == 3


def test_user_agent_header_is_sent(companyfacts_payload: Any) -> None:
    with respx.mock() as router:
        route = router.get(FACTS_URL).mock(
            return_value=httpx.Response(200, json=companyfacts_payload)
        )
        with EdgarClient(_fast_settings(), backoff=0.0) as client:
            client.get_company_facts(320193)

    sent_ua = route.calls.last.request.headers["user-agent"]
    assert sent_ua == "Tessera Test test@example.com"


def test_rate_limiter_enforces_minimum_interval() -> None:
    clock = [1000.0]
    sleeps: list[float] = []
    limiter = _RateLimiter(
        2.0,  # 2 req/s -> 0.5s minimum interval
        monotonic=lambda: clock[0],
        sleep=sleeps.append,
    )

    limiter.acquire()  # first call: no wait
    limiter.acquire()  # second call (clock unchanged): must wait the interval

    assert sleeps == pytest.approx([0.5])
