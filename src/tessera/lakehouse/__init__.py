"""Iceberg bronze lakehouse: catalog, table schemas, and write path.

This package owns the raw landing zone. Facts pulled from SEC are written as
immutable Iceberg bronze tables through a catalog seam (local: a SQLite-backed
``sql`` catalog over a filesystem warehouse; cloud: Glue over S3). The
:mod:`~tessera.warehouse` package then exposes these tables to DuckDB for dbt.
"""

from __future__ import annotations
