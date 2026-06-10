"""Build the small working ticker/CIK universe the pipeline runs against.

Resolves a list of ticker symbols to zero-padded SEC CIKs using the EDGAR
ticker map and writes the result to ``data/universe.json`` (path from
:class:`~tessera.config.Settings`). Every downstream stage — dlt extract, dbt
seed, the screener — reads this file to know which issuers are in scope.

Run it directly::

    python -m scripts.seed_universe --tickers AAPL,MSFT,GOOGL,AMZN,NVDA

or via the task wrapper ``inv seed``. Pass ``--offline`` to resolve against a
local copy of ``company_tickers.json`` (the test fixture by default) instead of
fetching the live map — useful for CI and demos without network access.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

from tessera.config import Settings, get_settings
from tessera.errors import ConfigError
from tessera.ingestion.edgar_client import EdgarClient
from tessera.ingestion.models import TickerMapEntry
from tessera.logging import configure_logging, get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence

# Default working universe for the local end-to-end run (mirrors tasks.DEFAULT_UNIVERSE).
DEFAULT_TICKERS = ("AAPL", "MSFT", "GOOGL", "AMZN", "NVDA")

# Offline ticker-map source: the trimmed fixture checked into the test suite.
OFFLINE_TICKER_MAP = Path("tests/fixtures/company_tickers.json")

_log = get_logger("scripts.seed_universe")


class UniverseEntry(BaseModel):
    """One resolved issuer in the working universe."""

    ticker: str
    cik: int
    cik_padded: str
    title: str


def _index_by_ticker(ticker_map: Sequence[TickerMapEntry]) -> dict[str, TickerMapEntry]:
    """Return the ticker map keyed by upper-cased ticker for O(1) lookup."""
    return {entry.ticker.upper(): entry for entry in ticker_map}


def resolve_universe(
    ticker_map: Sequence[TickerMapEntry], tickers: Sequence[str]
) -> list[UniverseEntry]:
    """Resolve ticker symbols to universe entries against a ticker map.

    Args:
        ticker_map: The ticker -> CIK directory to resolve against.
        tickers: The requested ticker symbols (case-insensitive).

    Returns:
        One :class:`UniverseEntry` per requested ticker, in request order.

    Raises:
        ConfigError: If any requested ticker is absent from the map.
    """
    index = _index_by_ticker(ticker_map)
    resolved: list[UniverseEntry] = []
    missing: list[str] = []
    for ticker in tickers:
        entry = index.get(ticker.upper())
        if entry is None:
            missing.append(ticker.upper())
            continue
        resolved.append(
            UniverseEntry(
                ticker=entry.ticker.upper(),
                cik=entry.cik,
                cik_padded=f"{entry.cik:010d}",
                title=entry.title,
            )
        )
    if missing:
        raise ConfigError(f"tickers not found in EDGAR ticker map: {', '.join(missing)}")
    return resolved


def build_universe(client: EdgarClient, tickers: Sequence[str]) -> list[UniverseEntry]:
    """Resolve tickers to universe entries via the live EDGAR ticker map.

    Args:
        client: The SEC client used to fetch ``company_tickers.json``.
        tickers: The requested ticker symbols (case-insensitive).

    Returns:
        One :class:`UniverseEntry` per requested ticker, in request order.
    """
    return resolve_universe(client.get_ticker_map(), tickers)


def load_offline_ticker_map(path: Path) -> list[TickerMapEntry]:
    """Load and parse a local ``company_tickers.json`` file.

    Args:
        path: Path to a ``company_tickers.json``-shaped file.

    Returns:
        One :class:`TickerMapEntry` per row.

    Raises:
        ConfigError: If the file does not exist.
    """
    if not path.exists():
        raise ConfigError(f"offline ticker map not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [TickerMapEntry.model_validate(row) for row in raw.values()]


def write_universe(entries: Sequence[UniverseEntry], path: Path) -> None:
    """Write universe entries to ``path`` as pretty-printed JSON.

    Args:
        entries: The resolved universe to persist.
        path: Destination file; parent directories are created as needed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [entry.model_dump() for entry in entries]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_universe(path: Path) -> list[UniverseEntry]:
    """Read a previously seeded universe file.

    Args:
        path: The ``universe.json`` file written by :func:`write_universe`.

    Returns:
        The parsed universe entries.

    Raises:
        ConfigError: If the file does not exist.
    """
    if not path.exists():
        raise ConfigError(f"universe not seeded; run `inv seed` first (missing {path})")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [UniverseEntry.model_validate(row) for row in raw]


def seed(
    tickers: Sequence[str],
    *,
    settings: Settings | None = None,
    offline: bool = False,
    offline_path: Path = OFFLINE_TICKER_MAP,
) -> list[UniverseEntry]:
    """Resolve ``tickers`` and write the universe file, returning the entries.

    Args:
        tickers: The requested ticker symbols.
        settings: Application settings; defaults to the process-wide instance.
        offline: When ``True``, resolve against ``offline_path`` instead of the
            live ticker map.
        offline_path: Local ticker-map file used in offline mode.

    Returns:
        The resolved universe entries (also written to ``settings.universe_path``).
    """
    settings = settings or get_settings()
    if offline:
        entries = resolve_universe(load_offline_ticker_map(offline_path), tickers)
    else:
        with EdgarClient(settings) as client:
            entries = build_universe(client, tickers)
    write_universe(entries, settings.universe_path)
    _log.info(
        "universe_seeded",
        count=len(entries),
        path=str(settings.universe_path),
        offline=offline,
    )
    return entries


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Parse command-line arguments for the seed script."""
    parser = argparse.ArgumentParser(
        prog="seed_universe",
        description="Resolve tickers to CIKs and write data/universe.json.",
    )
    parser.add_argument(
        "--tickers",
        default=",".join(DEFAULT_TICKERS),
        help="Comma-separated ticker symbols (default: %(default)s).",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Resolve against a local company_tickers.json instead of the live map.",
    )
    parser.add_argument(
        "--offline-path",
        type=Path,
        default=OFFLINE_TICKER_MAP,
        help="Local ticker-map file for --offline mode (default: %(default)s).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point: seed the working universe.

    Args:
        argv: Argument vector; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code (0 on success, 1 on a configuration error).
    """
    args = _parse_args(argv)
    settings = get_settings()
    configure_logging(settings)
    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    try:
        entries = seed(
            tickers,
            settings=settings,
            offline=args.offline,
            offline_path=args.offline_path,
        )
    except ConfigError as exc:
        _log.error("seed_failed", error=str(exc))
        return 1
    _log.info("seed_complete", tickers=[e.ticker for e in entries])
    return 0


if __name__ == "__main__":
    sys.exit(main())
