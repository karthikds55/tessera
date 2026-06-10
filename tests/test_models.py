"""Tests for pydantic payload parsing and fact flattening."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from tessera.ingestion.models import (
    CompanyFacts,
    FrameResponse,
    Submissions,
    TickerMapEntry,
    flatten_company_facts,
)

if TYPE_CHECKING:
    from typing import Any


def test_company_facts_parses(companyfacts_payload: Any) -> None:
    facts = CompanyFacts.model_validate(companyfacts_payload)

    assert facts.cik == 320193
    assert facts.entity_name == "Apple Inc."
    assert "Revenues" in facts.facts["us-gaap"]


def test_flatten_company_facts_row_shape(companyfacts_payload: Any) -> None:
    facts = CompanyFacts.model_validate(companyfacts_payload)

    rows = flatten_company_facts(facts)

    # 2 Revenues + 1 NetIncomeLoss + 1 Assets = 4 facts.
    assert len(rows) == 4

    revenue_2023 = next(row for row in rows if row.raw_tag == "Revenues" and row.fy == 2023)
    assert revenue_2023.cik == 320193
    assert revenue_2023.taxonomy == "us-gaap"
    assert revenue_2023.unit == "USD"
    assert revenue_2023.value == 383285000000
    assert revenue_2023.form == "10-K"
    assert revenue_2023.end == date(2023, 9, 30)
    assert revenue_2023.accn == "0000320193-23-000106"


def test_frame_response_parses(frames_payload: Any) -> None:
    frame = FrameResponse.model_validate(frames_payload)

    assert frame.tag == "Revenues"
    assert frame.ccp == "CY2023"
    assert len(frame.data) == 2
    assert frame.data[0].cik == 320193
    assert frame.data[0].val == 383285000000


def test_submissions_parses(submissions_payload: Any) -> None:
    submissions = Submissions.model_validate(submissions_payload)

    assert submissions.cik == "320193"
    assert submissions.tickers == ["AAPL"]
    assert submissions.sic == "3571"
    assert submissions.state_of_incorporation == "CA"
    assert submissions.fiscal_year_end == "0928"
    assert submissions.filings.recent.form == ["10-K", "10-Q"]


def test_ticker_map_parses(ticker_map_payload: Any) -> None:
    entries = [TickerMapEntry.model_validate(v) for v in ticker_map_payload.values()]

    assert len(entries) == 3
    apple = next(entry for entry in entries if entry.ticker == "AAPL")
    assert apple.cik == 320193
    assert apple.title == "Apple Inc."
