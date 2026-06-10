"""Tests for the seed-universe script: ticker -> CIK resolution, offline mode, IO.

All resolution runs against the trimmed ``company_tickers.json`` fixture with a
mocked client; no live SEC requests are made.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from scripts.seed_universe import (
    build_universe,
    load_offline_ticker_map,
    read_universe,
    resolve_universe,
    seed,
    write_universe,
)

from tessera.config import Settings
from tessera.errors import ConfigError
from tessera.ingestion.edgar_client import EdgarClient
from tessera.ingestion.models import TickerMapEntry

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

FIXTURE_PATH = "tests/fixtures/company_tickers.json"


def _ticker_map(payload: dict[str, Any]) -> list[TickerMapEntry]:
    """Parse a company_tickers.json payload into model rows."""
    return [TickerMapEntry.model_validate(row) for row in payload.values()]


def test_resolve_universe_resolves_in_request_order(ticker_map_payload: Any) -> None:
    entries = resolve_universe(_ticker_map(ticker_map_payload), ["MSFT", "AAPL"])

    assert [e.ticker for e in entries] == ["MSFT", "AAPL"]
    assert entries[1].cik == 320193
    assert entries[1].cik_padded == "0000320193"
    assert entries[1].title == "Apple Inc."


def test_resolve_universe_is_case_insensitive(ticker_map_payload: Any) -> None:
    entries = resolve_universe(_ticker_map(ticker_map_payload), ["aapl"])

    assert entries[0].ticker == "AAPL"
    assert entries[0].cik == 320193


def test_resolve_universe_raises_on_unknown_ticker(ticker_map_payload: Any) -> None:
    with pytest.raises(ConfigError, match="ZZZZ"):
        resolve_universe(_ticker_map(ticker_map_payload), ["AAPL", "ZZZZ"])


def test_build_universe_uses_client_ticker_map(
    ticker_map_payload: Any, mocker: MockerFixture
) -> None:
    client = mocker.Mock(spec=EdgarClient)
    client.get_ticker_map.return_value = _ticker_map(ticker_map_payload)

    entries = build_universe(client, ["GOOGL"])

    client.get_ticker_map.assert_called_once_with()
    assert entries[0].cik == 1652044
    assert entries[0].cik_padded == "0001652044"


def test_load_offline_ticker_map_reads_fixture(repo_root: Path) -> None:
    ticker_map = load_offline_ticker_map(repo_root / FIXTURE_PATH)

    tickers = {entry.ticker for entry in ticker_map}
    assert {"AAPL", "MSFT", "GOOGL"} == tickers


def test_load_offline_ticker_map_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="offline ticker map not found"):
        load_offline_ticker_map(tmp_path / "nope.json")


def test_write_then_read_universe_roundtrips(ticker_map_payload: Any, tmp_path: Path) -> None:
    entries = resolve_universe(_ticker_map(ticker_map_payload), ["AAPL", "MSFT"])
    path = tmp_path / "universe.json"

    write_universe(entries, path)
    loaded = read_universe(path)

    assert loaded == entries


def test_read_universe_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="universe not seeded"):
        read_universe(tmp_path / "universe.json")


def test_seed_offline_writes_universe_file(repo_root: Path, tmp_path: Path) -> None:
    settings = Settings(profile="local", data_dir=tmp_path)

    entries = seed(
        ["AAPL", "MSFT"],
        settings=settings,
        offline=True,
        offline_path=repo_root / FIXTURE_PATH,
    )

    assert [e.ticker for e in entries] == ["AAPL", "MSFT"]
    assert settings.universe_path.exists()
    assert read_universe(settings.universe_path) == entries
