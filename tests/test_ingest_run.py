"""End-to-end test for the ingest runner: dlt extract-load then Iceberg landing.

A fake EDGAR client keeps it offline, but the *real* dlt pipeline, DuckDB
destination, Iceberg catalog/write path, and bronze landing all run against temp
dirs — so this exercises the whole local ``inv ingest`` flow, including the
re-aggregation of dlt's ``submissions__tickers`` child table.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from tessera.config import Settings
from tessera.ingestion import run
from tessera.ingestion.models import (
    CompanyFacts,
    Submissions,
    TickerMapEntry,
    flatten_company_facts,
)

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any


def _local_settings(tmp_path: Path) -> Settings:
    """Build a local-profile Settings pointed entirely at a temp tree."""
    return Settings(
        profile="local",
        data_dir=tmp_path / "data",
        duckdb_path=tmp_path / "data" / "tessera.duckdb",
        iceberg_catalog_uri=f"sqlite:///{(tmp_path / 'catalog.db').as_posix()}",
        iceberg_warehouse=str(tmp_path / "warehouse"),
    )


def _seed_universe(settings: Settings) -> None:
    """Write a one-issuer universe file where run_ingest expects it."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.universe_path.write_text(
        json.dumps(
            [{"ticker": "AAPL", "cik": 320193, "cik_padded": "0000320193", "title": "Apple Inc."}]
        ),
        encoding="utf-8",
    )


@pytest.mark.integration
def test_run_ingest_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    companyfacts_payload: Any,
    submissions_payload: Any,
) -> None:
    facts = CompanyFacts.model_validate(companyfacts_payload)
    submissions = Submissions.model_validate(submissions_payload)

    class FakeEdgarClient:
        def __init__(self, _settings: Settings) -> None:
            pass

        def __enter__(self) -> FakeEdgarClient:
            return self

        def __exit__(self, *_exc: object) -> bool:
            return False

        def get_ticker_map(self) -> list[TickerMapEntry]:
            return [TickerMapEntry(cik_str=320193, ticker="AAPL", title="Apple Inc.")]

        def get_company_facts(self, _cik: int | str) -> CompanyFacts:
            return facts

        def get_submissions(self, _cik: int | str) -> Submissions:
            return submissions

    monkeypatch.setattr(run, "EdgarClient", FakeEdgarClient)

    settings = _local_settings(tmp_path)
    _seed_universe(settings)

    views = run.run_ingest(settings)

    assert set(views) == {"bronze_company_facts", "bronze_submissions", "bronze_ticker_map"}

    # The registered DuckDB views must expose the landed bronze rows.
    from tessera.lakehouse.catalog import build_catalog
    from tessera.warehouse.duckdb_io import connect, register_bronze_views

    conn = connect(settings)
    try:
        register_bronze_views(conn, build_catalog(settings))
        fact_count = conn.execute("SELECT count(*) FROM bronze_company_facts").fetchone()
        assert fact_count is not None
        assert fact_count[0] == len(flatten_company_facts(facts))

        # tickers spilled by dlt into a child table are re-aggregated to CSV.
        tickers = conn.execute(
            "SELECT tickers FROM bronze_submissions WHERE cik = '320193'"
        ).fetchone()
        assert tickers is not None and tickers[0] == "AAPL"

        mapped = conn.execute("SELECT ticker FROM bronze_ticker_map").fetchone()
        assert mapped is not None and mapped[0] == "AAPL"
    finally:
        conn.close()
