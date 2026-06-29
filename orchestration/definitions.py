"""Software-defined asset graph for the tessera EDGAR pipeline.

The pipeline is modelled as five assets:

``ticker_universe`` → ``raw_companyfacts`` → ``iceberg_bronze`` → ``dbt_models``
→ ``fundamentals_mart``

Every asset delegates to the same library functions the ``inv`` tasks use — the
``scripts.seed_universe`` seeder, :mod:`tessera.ingestion`/:mod:`tessera.lakehouse`
for extract-load + landing, and a thin shell of ``dbt build`` for the transform
layer — so there is one implementation of the pipeline, orchestrated two ways.

**Design choices (documented per the plan):**

- *dbt integration:* a thin op that shells ``uv run dbt build`` rather than
  ``dagster-dbt``/``@dbt_assets``. This keeps the dependency surface small and
  avoids coupling the asset graph to a parsed dbt manifest; the trade-off is that
  the individual dbt models are one opaque Dagster asset rather than many.
- *Partitions:* the two upstream extract assets are partitioned by fiscal year
  (:class:`StaticPartitionsDefinition`). The current ingest pulls full history
  per run, so today the partition key scopes logging/metadata; per-partition
  incremental extraction is a typed ``TODO`` (see :func:`raw_companyfacts`).
- *Sensor:* a real-but-simple poll of the maximum ``filed`` date in bronze; the
  deep per-accession diff is left as a documented ``TODO`` rather than a brittle
  first pass.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetSelection,
    Definitions,
    MaterializeResult,
    RunRequest,
    ScheduleDefinition,
    SensorResult,
    SkipReason,
    StaticPartitionsDefinition,
    asset,
    asset_check,
    define_asset_job,
    sensor,
)

from tessera.config import get_settings
from tessera.logging import configure_logging, get_logger

if TYPE_CHECKING:
    import duckdb
    from dagster import AssetExecutionContext, SensorEvaluationContext

_log = get_logger("orchestration.definitions")

# Repo paths resolved relative to this file (orchestration/definitions.py).
_REPO_ROOT = Path(__file__).resolve().parents[1]
_DBT_PROJECT_DIR = _REPO_ROOT / "dbt" / "edgar"

# Fully-qualified mart relations: dbt writes marts to the `main_marts` schema
# (profile base schema `main` + the `marts` custom schema from dbt_project.yml).
_MART_SCHEMA = "main_marts"
_FUNDAMENTALS_MART = f"{_MART_SCHEMA}.mart_fundamentals_annual"
_FCT_FINANCIALS = f"{_MART_SCHEMA}.fct_financials"
_DIM_COMPANY = f"{_MART_SCHEMA}.dim_company"

# Fiscal years the upstream extract assets are partitioned over. SEC company
# facts coverage is reliable from ~2009; we cap at the current calendar year.
_FIRST_FISCAL_YEAR = 2009
fiscal_year_partitions = StaticPartitionsDefinition(
    [str(year) for year in range(_FIRST_FISCAL_YEAR, datetime.now(tz=timezone.utc).year + 1)]
)


# --- Assets ------------------------------------------------------------------
@asset(group_name="ingest")
def ticker_universe(context: AssetExecutionContext) -> MaterializeResult:
    """Resolve the working tickers to CIKs and write ``data/universe.json``.

    Delegates to :func:`scripts.seed_universe.seed`; the resulting universe file
    is what every downstream stage reads to know which issuers are in scope.
    """
    from scripts.seed_universe import DEFAULT_TICKERS, seed

    settings = get_settings()
    configure_logging(settings)
    entries = seed(list(DEFAULT_TICKERS), settings=settings)
    context.log.info("seeded %d companies", len(entries))
    return MaterializeResult(
        metadata={"num_companies": len(entries), "tickers": ", ".join(e.ticker for e in entries)}
    )


@asset(deps=[ticker_universe], partitions_def=fiscal_year_partitions, group_name="ingest")
def raw_companyfacts(context: AssetExecutionContext) -> MaterializeResult:
    """Extract-load SEC company facts for the seeded universe into DuckDB via dlt.

    Runs the full ingest (extract-load → Iceberg landing → view registration)
    through :func:`tessera.ingestion.run.run_ingest`, the same function ``inv
    ingest`` calls.

    TODO(partitions): ``run_ingest`` currently pulls each issuer's full filing
    history in one pass, so the fiscal-year ``partition_key`` here scopes
    logging/metadata only. Per-partition incremental extraction (passing the
    fiscal year down to the dlt source's ``filed`` cursor) is future work.
    """
    from tessera.ingestion.run import run_ingest

    settings = get_settings()
    fiscal_year = context.partition_key
    context.log.info("ingesting (fiscal_year partition=%s, full-history pull)", fiscal_year)
    views = run_ingest(settings)
    return MaterializeResult(
        metadata={"fiscal_year": fiscal_year, "bronze_views": ", ".join(views)}
    )


@asset(deps=[raw_companyfacts], partitions_def=fiscal_year_partitions, group_name="ingest")
def iceberg_bronze(context: AssetExecutionContext) -> MaterializeResult:
    """Expose the landed Iceberg bronze tables as DuckDB views for dbt.

    The landing + view registration happens inside :func:`run_ingest` (driven by
    :func:`raw_companyfacts`); this asset re-registers the views to surface the
    current bronze row counts as materialization metadata and to give the dbt
    transform a distinct, observable upstream node.
    """
    from tessera.lakehouse.catalog import build_catalog, ensure_namespace
    from tessera.warehouse.duckdb_io import connect, register_bronze_views

    settings = get_settings()
    catalog = build_catalog(settings)
    ensure_namespace(catalog)
    conn = connect(settings)
    try:
        views = register_bronze_views(conn, catalog)
        counts = {view: _scalar_int(conn, f"SELECT count(*) FROM {view}") for view in views}
    finally:
        conn.close()
    context.log.info("registered bronze views: %s", counts)
    return MaterializeResult(metadata={"partition": context.partition_key, **counts})


@asset(deps=[iceberg_bronze], group_name="transform")
def dbt_models(context: AssetExecutionContext) -> MaterializeResult:
    """Build the dbt models (seed → staging → marts) on the DuckDB target.

    Shells ``uv run dbt build`` in ``dbt/edgar`` — the same command ``inv build``
    runs — rather than embedding ``dagster-dbt``; see the module docstring for the
    rationale. Raises if dbt returns a non-zero exit code so the run fails loudly.
    """
    context.log.info("running dbt build in %s", _DBT_PROJECT_DIR)
    result = subprocess.run(  # noqa: S603 - fixed command, no user input
        ["uv", "run", "dbt", "build"],
        cwd=_DBT_PROJECT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        context.log.error(result.stdout[-2000:])
        raise RuntimeError(f"dbt build failed (exit {result.returncode}): {result.stderr[-2000:]}")
    return MaterializeResult(metadata={"dbt_output_tail": result.stdout[-1000:]})


@asset(deps=[dbt_models], group_name="transform")
def fundamentals_mart(context: AssetExecutionContext) -> MaterializeResult:
    """Surface the wide company-year fundamentals mart as the pipeline's leaf asset.

    Reads the row count and fiscal-year span of ``mart_fundamentals_annual`` so the
    final asset carries observable freshness/size metadata.
    """
    settings = get_settings()
    from tessera.warehouse.duckdb_io import connect

    conn = connect(settings)
    try:
        rows = _scalar_int(conn, f"SELECT count(*) FROM {_FUNDAMENTALS_MART}")
        latest = _scalar_int(conn, f"SELECT max(fiscal_year) FROM {_FUNDAMENTALS_MART}")
    finally:
        conn.close()
    context.log.info("fundamentals_mart rows=%d latest_fy=%s", rows, latest)
    return MaterializeResult(metadata={"num_rows": rows, "latest_fiscal_year": latest})


# --- Asset checks (mirror the dbt DQ rules) ----------------------------------
@asset_check(asset=fundamentals_mart, description="One row per (cik, fiscal_year) in the mart.")
def mart_grain_is_unique() -> AssetCheckResult:
    """Fail if any ``(cik, fiscal_year)`` appears more than once in the mart."""
    sql = f"""
        SELECT count(*) FROM (
            SELECT cik, fiscal_year FROM {_FUNDAMENTALS_MART}
            GROUP BY cik, fiscal_year HAVING count(*) > 1
        )
    """
    duplicates = _check_scalar(sql)
    return AssetCheckResult(passed=duplicates == 0, metadata={"duplicate_grains": duplicates})


@asset_check(asset=fundamentals_mart, description="Every fact's cik exists in dim_company.")
def fact_referential_integrity() -> AssetCheckResult:
    """Fail if any ``fct_financials.cik`` has no matching ``dim_company`` row."""
    sql = f"""
        SELECT count(*) FROM {_FCT_FINANCIALS} f
        LEFT JOIN {_DIM_COMPANY} d ON f.cik = d.cik
        WHERE d.cik IS NULL
    """
    orphans = _check_scalar(sql)
    return AssetCheckResult(passed=orphans == 0, metadata={"orphan_facts": orphans})


@asset_check(asset=fundamentals_mart, description="net_margin stays within sane bounds.")
def net_margin_within_bounds() -> AssetCheckResult:
    """Warn if any non-null ``net_margin`` falls outside ``[-10, 10]``."""
    sql = f"""
        SELECT count(*) FROM {_FUNDAMENTALS_MART}
        WHERE net_margin IS NOT NULL AND (net_margin < -10 OR net_margin > 10)
    """
    out_of_range = _check_scalar(sql)
    return AssetCheckResult(
        passed=out_of_range == 0,
        severity=AssetCheckSeverity.WARN,
        metadata={"out_of_range_rows": out_of_range},
    )


@asset_check(asset=fundamentals_mart, description="Latest fiscal year is reasonably recent.")
def fundamentals_are_fresh() -> AssetCheckResult:
    """Warn if the newest fiscal year in the mart is more than two years stale."""
    latest = _check_scalar(f"SELECT max(fiscal_year) FROM {_FUNDAMENTALS_MART}")
    threshold = datetime.now(tz=timezone.utc).year - 2
    return AssetCheckResult(
        passed=latest >= threshold,
        severity=AssetCheckSeverity.WARN,
        metadata={"latest_fiscal_year": latest, "min_acceptable": threshold},
    )


# --- Jobs, schedule, sensor --------------------------------------------------
# Extract-load is partitioned by fiscal year; the transform layer is not.
ingest_job = define_asset_job(
    "ingest_job", selection=AssetSelection.assets(raw_companyfacts, iceberg_bronze)
)
transform_job = define_asset_job(
    "transform_job", selection=AssetSelection.assets(dbt_models, fundamentals_mart)
)

# Weekly rebuild of the marts from whatever bronze is current.
weekly_refresh_schedule = ScheduleDefinition(
    name="weekly_mart_refresh",
    job=transform_job,
    cron_schedule="0 6 * * 1",  # Mondays 06:00 UTC
    execution_timezone="UTC",
)


@sensor(job=ingest_job, minimum_interval_seconds=3600)
def new_filings_sensor(context: SensorEvaluationContext) -> SensorResult | SkipReason:
    """Trigger an ingest of the latest fiscal year when new filings appear.

    Polls the maximum ``filed`` date in the bronze company-facts view and stores
    it in the sensor cursor; a newer value requests a run for the current fiscal
    year's partition.

    TODO(diff): this is a coarse high-watermark check. Real new-filing detection
    should diff submissions' accession numbers against the last-seen set and emit
    one targeted run per newly filed accession.
    """
    settings = get_settings()
    from tessera.warehouse.duckdb_io import connect

    try:
        conn = connect(settings)
    except Exception as exc:  # noqa: BLE001 - warehouse not built yet is a normal skip
        return SkipReason(f"warehouse unavailable: {exc}")
    try:
        row = conn.execute("SELECT max(filed) FROM bronze_company_facts").fetchone()
    except Exception as exc:  # noqa: BLE001 - bronze not landed yet is a normal skip
        return SkipReason(f"bronze not available: {exc}")
    finally:
        conn.close()

    latest_filed = str(row[0]) if row and row[0] is not None else ""
    if not latest_filed:
        return SkipReason("no filings landed yet")
    if latest_filed == context.cursor:
        return SkipReason(f"no new filings since {latest_filed}")

    current_fy = str(datetime.now(tz=timezone.utc).year)
    context.log.info("new filings detected (max filed=%s); requesting ingest", latest_filed)
    return SensorResult(
        run_requests=[RunRequest(partition_key=current_fy)],
        cursor=latest_filed,
    )


# --- Helpers -----------------------------------------------------------------
def _scalar_int(conn: duckdb.DuckDBPyConnection, sql: str) -> int:
    """Execute ``sql`` and return its single scalar as an int (0 if NULL/empty)."""
    row = conn.execute(sql).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _check_scalar(sql: str) -> int:
    """Open the warehouse, run a scalar count query for an asset check, and close it."""
    settings = get_settings()
    from tessera.warehouse.duckdb_io import connect

    conn = connect(settings)
    try:
        return _scalar_int(conn, sql)
    finally:
        conn.close()


defs = Definitions(
    assets=[ticker_universe, raw_companyfacts, iceberg_bronze, dbt_models, fundamentals_mart],
    asset_checks=[
        mart_grain_is_unique,
        fact_referential_integrity,
        net_margin_within_bounds,
        fundamentals_are_fresh,
    ],
    jobs=[ingest_job, transform_job],
    schedules=[weekly_refresh_schedule],
    sensors=[new_filings_sensor],
)
