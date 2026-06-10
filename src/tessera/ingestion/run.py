"""Run the dlt extract-load over the seeded universe (``inv ingest``).

Reads the working universe written by :mod:`scripts.seed_universe`, then runs the
:func:`~tessera.ingestion.sources.edgar_source` pipeline into the local DuckDB
destination dlt manages. This is the EL half of the pipeline; the Iceberg bronze
landing is added in PR-05, which consumes the DuckDB/parquet output produced here.
Until then ``inv ingest`` stops at this dlt load step.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import dlt

from tessera.config import get_settings
from tessera.ingestion.edgar_client import EdgarClient
from tessera.ingestion.sources import edgar_source
from tessera.logging import configure_logging, get_logger

if TYPE_CHECKING:
    from tessera.config import Settings

_log = get_logger("tessera.ingestion.run")


def _build_pipeline(settings: Settings) -> Any:
    """Construct the dlt pipeline writing to the local DuckDB destination.

    Args:
        settings: Application settings supplying the pipeline name, dataset, and
            DuckDB path.

    Returns:
        The configured dlt pipeline.
    """
    return dlt.pipeline(
        pipeline_name=settings.dlt_pipeline_name,
        destination=dlt.destinations.duckdb(str(settings.duckdb_path)),
        dataset_name=settings.dlt_dataset_name,
    )


def run_ingest(settings: Settings | None = None) -> Any:
    """Extract EDGAR facts for the seeded universe and load them to DuckDB bronze.

    Args:
        settings: Application settings; defaults to the process-wide instance.

    Returns:
        The dlt load info for the run.
    """
    from scripts.seed_universe import read_universe  # noqa: PLC0415 — avoid import cycle

    settings = settings or get_settings()
    configure_logging(settings)

    entries = read_universe(settings.universe_path)
    ciks = [entry.cik_padded for entry in entries]
    _log.info("ingest_start", universe_size=len(ciks), pipeline=settings.dlt_pipeline_name)

    pipeline = _build_pipeline(settings)
    with EdgarClient(settings) as client:
        load_info = pipeline.run(edgar_source(client, ciks))

    _log.info("ingest_complete", pipeline=settings.dlt_pipeline_name)
    return load_info


def main() -> int:
    """CLI entry point for ``python -m tessera.ingestion.run``.

    Returns:
        Process exit code (0 on success).
    """
    load_info = run_ingest()
    _log.info("ingest_load_info", info=str(load_info))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
