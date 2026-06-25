"""Land dlt's DuckDB bronze output into the durable Iceberg bronze tables.

The dlt pipeline (:mod:`tessera.ingestion.sources`) extract-loads the three EDGAR
feeds into a DuckDB dataset. This module reads that dataset back as Arrow and
appends it to Iceberg bronze, reconstructing the columns dlt normalised away:

- ``company_facts`` and ``ticker_map`` land flat, with the ISO date/text columns
  dlt inferred cast back to the typed bronze grain.
- ``submissions`` has its ``tickers``/``exchanges`` list columns spilled by dlt
  into child tables; we re-aggregate them (ordered by ``_dlt_list_idx``) into the
  CSV-encoded bronze columns.

The DuckDB read is projected to the exact bronze Arrow schemas and cast before
append, so a nullable DuckDB column never trips Iceberg's required-field check.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tessera.lakehouse import schemas, writers
from tessera.logging import get_logger

if TYPE_CHECKING:
    import duckdb
    import pyarrow as pa

    from tessera.lakehouse.catalog import Catalog

_log = get_logger("tessera.lakehouse.landing")

_FACTS_SQL = """
    SELECT cik, taxonomy, raw_tag, unit, value,
           CAST(fy AS INTEGER) AS fy, fp, form, frame, accn,
           CAST(start AS DATE) AS start,
           CAST("end" AS DATE) AS "end",
           CAST(filed AS DATE) AS filed
    FROM {dataset}.company_facts
"""

_TICKER_MAP_SQL = "SELECT cik, ticker, title FROM {dataset}.ticker_map"


def _table_exists(conn: duckdb.DuckDBPyConnection, dataset: str, name: str) -> bool:
    """Return whether ``dataset.name`` exists in the DuckDB catalog."""
    row = conn.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = ? AND table_name = ?",
        [dataset, name],
    ).fetchone()
    return row is not None


def _child_csv_expr(dataset: str, child: str, alias: str) -> tuple[str, str]:
    """Build the SELECT expression and LEFT JOIN that re-aggregate a dlt list table.

    Args:
        dataset: The DuckDB schema dlt loaded into.
        child: The dlt child table name (e.g. ``submissions__tickers``).
        alias: The output column / subquery alias (e.g. ``tickers``).

    Returns:
        A ``(select_expr, join_clause)`` pair the submissions query stitches in.
    """
    select_expr = f"{alias}_t.{alias}"
    join_clause = (
        f" LEFT JOIN ("
        f"SELECT _dlt_parent_id, string_agg(value, ',' ORDER BY _dlt_list_idx) AS {alias} "
        f"FROM {dataset}.{child} GROUP BY _dlt_parent_id) {alias}_t "
        f"ON {alias}_t._dlt_parent_id = s._dlt_id"
    )
    return select_expr, join_clause


def _submissions_sql(conn: duckdb.DuckDBPyConnection, dataset: str) -> str:
    """Build the submissions projection, re-aggregating present child list tables."""
    columns: dict[str, str] = {
        "tickers": "CAST(NULL AS VARCHAR)",
        "exchanges": "CAST(NULL AS VARCHAR)",
    }
    joins = ""
    for alias in ("tickers", "exchanges"):
        if _table_exists(conn, dataset, f"submissions__{alias}"):
            select_expr, join_clause = _child_csv_expr(dataset, f"submissions__{alias}", alias)
            columns[alias] = select_expr
            joins += join_clause
    return (
        f"SELECT s.cik, s.name, {columns['tickers']} AS tickers, "
        f"{columns['exchanges']} AS exchanges, s.sic, s.sic_description, "
        f"s.state_of_incorporation, s.fiscal_year_end "
        f"FROM {dataset}.submissions s{joins}"
    )


def land_bronze_from_duckdb(
    conn: duckdb.DuckDBPyConnection, catalog: Catalog, dataset: str = "bronze"
) -> dict[str, int]:
    """Append dlt's loaded DuckDB ``dataset`` into the Iceberg bronze tables.

    Args:
        conn: An open DuckDB connection over the database dlt loaded into.
        catalog: The Iceberg catalog to write bronze tables in.
        dataset: The DuckDB schema dlt loaded into (its ``dataset_name``).

    Returns:
        Rows appended per bronze table identifier.
    """
    specs = (
        (
            schemas.COMPANY_FACTS_TABLE,
            schemas.COMPANY_FACTS_SCHEMA,
            schemas.COMPANY_FACTS_PARTITION_SPEC,
            _FACTS_SQL.format(dataset=dataset),
            schemas.COMPANY_FACTS_ARROW_SCHEMA,
        ),
        (
            schemas.SUBMISSIONS_TABLE,
            schemas.SUBMISSIONS_SCHEMA,
            schemas.UNPARTITIONED,
            _submissions_sql(conn, dataset),
            schemas.SUBMISSIONS_ARROW_SCHEMA,
        ),
        (
            schemas.TICKER_MAP_TABLE,
            schemas.TICKER_MAP_SCHEMA,
            schemas.UNPARTITIONED,
            _TICKER_MAP_SQL.format(dataset=dataset),
            schemas.TICKER_MAP_ARROW_SCHEMA,
        ),
    )

    landed: dict[str, int] = {}
    for identifier, schema, partition_spec, sql, arrow_schema in specs:
        # Project to the bronze schema (column order matches) and cast so the
        # DuckDB-nullable columns satisfy the required Iceberg fields.
        arrow: pa.Table = conn.execute(sql).arrow().cast(arrow_schema)
        writers.create_table_if_absent(catalog, identifier, schema, partition_spec)
        landed[identifier] = writers.append_facts(catalog, identifier, arrow, evolve=False)
    _log.info("bronze_landed", **{k.replace(".", "_"): v for k, v in landed.items()})
    return landed
