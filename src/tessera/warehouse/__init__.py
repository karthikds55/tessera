"""DuckDB warehouse: expose the Iceberg bronze tables to SQL and dbt.

DuckDB is the local query/transform engine. This package opens the warehouse
connection and registers the Iceberg bronze tables as DuckDB relations so dbt's
duckdb target can read them. See :mod:`tessera.warehouse.duckdb_io`.
"""

from __future__ import annotations
