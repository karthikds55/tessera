"""Run the EDGAR ingest over the seeded universe (``inv ingest``).

Two stages, end to end:

1. **Extract-load** — the :func:`~tessera.ingestion.sources.edgar_source` dlt
   pipeline pulls the working universe (written by :mod:`scripts.seed_universe`)
   into the DuckDB dataset dlt manages, handling incremental state and merges.
2. **Land** — :func:`~tessera.lakehouse.landing.land_bronze_from_duckdb` appends
   that DuckDB output into the durable Iceberg bronze tables, which are then
   registered as DuckDB views for dbt to read.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import dlt

from tessera.config import get_settings
from tessera.ingestion.edgar_client import EdgarClient
from tessera.ingestion.sources import edgar_source
from tessera.lakehouse.catalog import build_catalog, ensure_namespace
from tessera.lakehouse.landing import land_bronze_from_duckdb
from tessera.logging import configure_logging, get_logger
from tessera.warehouse.duckdb_io import connect, register_bronze_views

if TYPE_CHECKING:
    from tessera.config import Settings

_log = get_logger("tessera.ingestion.run")


def _build_pipeline(settings: Settings) -> Any:
    """Construct the dlt pipeline writing to the local DuckDB destination.

    Args:
        settings: Application settings supplying the pipeline name, dataset,
            DuckDB path, and data dir (which holds dlt's working state).

    Returns:
        The configured dlt pipeline.
    """
    return dlt.pipeline(
        pipeline_name=settings.dlt_pipeline_name,
        destination=dlt.destinations.duckdb(str(settings.duckdb_path)),
        dataset_name=settings.dlt_dataset_name,
        # Keep dlt's pipeline state under the project data dir so runs are
        # isolated per deployment (and per temp dir in tests).
        pipelines_dir=str(settings.data_dir / "dlt"),
    )


def run_ingest(settings: Settings | None = None) -> list[str]:
    """Extract EDGAR facts for the seeded universe and land them in Iceberg bronze.

    Args:
        settings: Application settings; defaults to the process-wide instance.

    Returns:
        The DuckDB view names registered over the Iceberg bronze tables.
    """
    from scripts.seed_universe import read_universe  # noqa: PLC0415 — avoid import cycle

    settings = settings or get_settings()
    configure_logging(settings)

    entries = read_universe(settings.universe_path)
    ciks = [entry.cik_padded for entry in entries]
    _log.info("ingest_start", universe_size=len(ciks), pipeline=settings.dlt_pipeline_name)

    pipeline = _build_pipeline(settings)
    with EdgarClient(settings) as client:
        pipeline.run(edgar_source(client, ciks))
    _log.info("dlt_load_complete", pipeline=settings.dlt_pipeline_name)

    catalog = build_catalog(settings)
    ensure_namespace(catalog)
    conn = connect(settings)
    try:
        landed = land_bronze_from_duckdb(conn, catalog, dataset=settings.dlt_dataset_name)
        views = register_bronze_views(conn, catalog)
    finally:
        conn.close()
    _log.info("ingest_complete", landed=landed, views=views)
    return views


def main() -> int:
    """CLI entry point for ``python -m tessera.ingestion.run``.

    Returns:
        Process exit code (0 on success).
    """
    views = run_ingest()
    _log.info("ingest_views", views=views)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
