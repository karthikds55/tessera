"""Shared pytest fixtures: sample SEC payloads and a Settings factory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tessera.config import Settings

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    """Load and parse a JSON fixture by file name."""
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture
def settings() -> Settings:
    """A deterministic local-profile Settings with a descriptive test User-Agent."""
    return Settings(profile="local", sec_user_agent="Tessera Test test@example.com")


@pytest.fixture
def companyfacts_payload() -> Any:
    """The sample companyfacts payload for Apple."""
    return load_fixture("companyfacts_AAPL.json")


@pytest.fixture
def frames_payload() -> Any:
    """The sample frames payload for us-gaap Revenues, CY2023."""
    return load_fixture("frames_revenue_2023.json")


@pytest.fixture
def submissions_payload() -> Any:
    """The sample submissions payload for Apple."""
    return load_fixture("submissions_AAPL.json")


@pytest.fixture
def ticker_map_payload() -> Any:
    """The trimmed ticker -> CIK map payload."""
    return load_fixture("company_tickers.json")
