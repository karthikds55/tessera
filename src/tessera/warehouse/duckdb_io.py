"""DuckDB connection and Iceberg-bronze registration for the dbt target.

:func:`connect` opens the warehouse DB and loads the ``iceberg``/``httpfs``
extensions. :func:`register_bronze_views` exposes each Iceberg bronze table to
DuckDB as a view so dbt sources can read it.

**Version-friction note (from the plan, confirmed on this stack):** DuckDB
1.0's ``iceberg`` extension cannot open the pyiceberg-written ``file://`` metadata
path on Windows (``iceberg_scan`` raises an IO error). We therefore attempt the
native ``iceberg_scan`` first and, on any failure, fall back to registering the
table's current Parquet data files directly (the Iceberg **write** path is
unaffected). The fallback still reads through the catalog snapshot — we resolve
data files from ``table.scan()`` — so it honours Iceberg's snapshot isolation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import duckdb

from tessera.lakehouse.catalog import BRONZE_NAMESPACE
from tessera.logging import get_logger

if TYPE_CHECKING:
    from tessera.config import Settings
    from tessera.lakehouse.catalog import Catalog

_log = get_logger("tessera.warehouse.duckdb_io")


def connect(settings: Settings) -> duckdb.DuckDBPyConnection:
    """Open the DuckDB warehouse and load the iceberg/httpfs extensions.

    Args:
        settings: Application settings supplying ``duckdb_path``.

    Returns:
        An open DuckDB connection. Extension loading is best-effort: if the
        extensions cannot be installed (e.g. offline), a warning is logged and
        the connection is still returned for the Parquet-fallback read path.
    """
    settings.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(settings.duckdb_path))
    for extension in ("httpfs", "iceberg"):
        try:
            conn.execute(f"INSTALL {extension}; LOAD {extension};")
        except duckdb.Error as exc:
            _log.warning("duckdb_extension_unavailable", extension=extension, error=str(exc))
    _log.info("duckdb_connected", path=str(settings.duckdb_path))
    return conn


def run_sql(conn: duckdb.DuckDBPyConnection, sql: str) -> duckdb.DuckDBPyConnection:
    """Execute ``sql`` on ``conn``, logging the statement.

    Args:
        conn: The DuckDB connection.
        sql: The SQL statement to execute.

    Returns:
        The connection (post-execution), for fetching results.
    """
    _log.debug("duckdb_exec", sql=sql)
    return conn.execute(sql)


def _view_name(identifier: tuple[str, ...]) -> str:
    """Flatten a ``(namespace, table)`` identifier into a DuckDB view name."""
    return "_".join(identifier)


def _data_file_paths(table: object) -> list[str]:
    """Return local Parquet data-file paths for the table's current snapshot."""
    paths: list[str] = []
    for task in table.scan().plan_files():  # type: ignore[attr-defined]
        path = str(task.file.file_path)
        # DuckDB read_parquet wants an OS path, not a file:// URI.
        paths.append(path.removeprefix("file://"))
    return paths


def register_bronze_views(
    conn: duckdb.DuckDBPyConnection, catalog: Catalog, namespace: str = BRONZE_NAMESPACE
) -> list[str]:
    """Register every bronze table in ``namespace`` as a DuckDB view.

    Tries the native ``iceberg_scan`` first; on failure falls back to reading the
    table's Parquet data files. Empty tables (no data files yet) are skipped.

    Args:
        conn: The DuckDB connection.
        catalog: The Iceberg catalog holding the bronze tables.
        namespace: The namespace to register; defaults to ``bronze``.

    Returns:
        The names of the views that were registered.
    """
    registered: list[str] = []
    for identifier in catalog.list_tables(namespace):
        view = _view_name(identifier)
        full_name = ".".join(identifier)
        table = catalog.load_table(full_name)
        metadata_location = str(table.metadata_location)

        try:
            run_sql(
                conn,
                f"CREATE OR REPLACE VIEW {view} AS "
                f"SELECT * FROM iceberg_scan('{metadata_location}')",
            )
            _log.info("bronze_view_registered", view=view, mode="iceberg_scan")
        except duckdb.Error as exc:
            _log.warning("iceberg_scan_failed", view=view, error=str(exc))
            paths = _data_file_paths(table)
            if not paths:
                _log.warning("bronze_view_skipped_empty", view=view)
                continue
            arrow = ", ".join(f"'{p}'" for p in paths)
            run_sql(conn, f"CREATE OR REPLACE VIEW {view} AS SELECT * FROM read_parquet([{arrow}])")
            _log.info("bronze_view_registered", view=view, mode="parquet_fallback")
        registered.append(view)
    return registered
