"""Seed Iceberg bronze from checked-in fixtures, offline, for CI.

CI must not depend on the SEC network, but the dbt build step needs bronze data.
This script swaps the live EDGAR client for one that serves the JSON fixtures
under ``tests/fixtures`` and then runs the *real* ingest path (dlt → Iceberg
landing → DuckDB view registration), so dbt builds against genuine — if tiny —
bronze tables without a single network call.

Run via ``inv ci-seed`` or ``python -m scripts.ci_seed``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from tessera.config import get_settings
from tessera.ingestion import run
from tessera.ingestion.models import CompanyFacts, Submissions, TickerMapEntry
from tessera.logging import configure_logging, get_logger

if TYPE_CHECKING:
    from tessera.config import Settings

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

# The single issuer the CI universe is seeded with (matches the fixtures).
_CI_UNIVERSE = [
    {"ticker": "AAPL", "cik": 320193, "cik_padded": "0000320193", "title": "Apple Inc."},
]

_log = get_logger("scripts.ci_seed")


def _load(name: str) -> object:
    """Load and parse a JSON fixture by file name."""
    return json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8"))


class _FixtureEdgarClient:
    """Offline ``EdgarClient`` stand-in that serves the checked-in JSON fixtures."""

    def __init__(self, _settings: Settings) -> None:
        """Parse the fixture payloads once (signature mirrors ``EdgarClient``)."""
        self._facts = CompanyFacts.model_validate(_load("companyfacts_AAPL.json"))
        self._submissions = Submissions.model_validate(_load("submissions_AAPL.json"))

    def __enter__(self) -> _FixtureEdgarClient:
        """Enter the context manager (no resources to acquire)."""
        return self

    def __exit__(self, *_exc: object) -> bool:
        """Exit the context manager without suppressing exceptions."""
        return False

    def get_ticker_map(self) -> list[TickerMapEntry]:
        """Return the one-issuer ticker map."""
        return [TickerMapEntry(cik_str=320193, ticker="AAPL", title="Apple Inc.")]

    def get_company_facts(self, _cik: int | str) -> CompanyFacts:
        """Return the fixture company-facts payload."""
        return self._facts

    def get_submissions(self, _cik: int | str) -> Submissions:
        """Return the fixture submissions payload."""
        return self._submissions


def ci_seed(settings: Settings | None = None) -> list[str]:
    """Seed Iceberg bronze from fixtures and register the DuckDB views.

    Args:
        settings: Application settings; defaults to the process-wide instance.

    Returns:
        The registered bronze view names.
    """
    settings = settings or get_settings()
    configure_logging(settings)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.universe_path.write_text(json.dumps(_CI_UNIVERSE), encoding="utf-8")
    # Offline injection: serve fixtures instead of calling SEC EDGAR. run_ingest
    # constructs ``run.EdgarClient(settings)``, so replacing the symbol suffices.
    run.EdgarClient = _FixtureEdgarClient  # type: ignore[assignment,misc]
    views = run.run_ingest(settings)
    _log.info("ci_seed_complete", views=views)
    return views


def main() -> int:
    """CLI entry point for ``python -m scripts.ci_seed``."""
    ci_seed()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
