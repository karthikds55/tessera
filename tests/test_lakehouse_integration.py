"""Integration tests for the Iceberg bronze write path against a real catalog.

These build a real SQLite-backed pyiceberg catalog over a temp filesystem
warehouse, so they exercise namespace creation, table creation, append, and the
additive schema-evolution branch in :mod:`tessera.lakehouse.writers`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyarrow as pa
import pytest

from tessera.config import Settings
from tessera.lakehouse import schemas, writers
from tessera.lakehouse.catalog import build_catalog, ensure_namespace

if TYPE_CHECKING:
    from pathlib import Path


def _local_settings(tmp_path: Path) -> Settings:
    return Settings(
        profile="local",
        data_dir=tmp_path / "data",
        iceberg_catalog_uri=f"sqlite:///{(tmp_path / 'catalog.db').as_posix()}",
        iceberg_warehouse=str(tmp_path / "warehouse"),
    )


@pytest.mark.integration
def test_create_append_and_read_back(tmp_path: Path) -> None:
    catalog = build_catalog(_local_settings(tmp_path))
    ensure_namespace(catalog)
    # ensure_namespace is idempotent.
    ensure_namespace(catalog)

    writers.create_table_if_absent(
        catalog,
        schemas.TICKER_MAP_TABLE,
        schemas.TICKER_MAP_SCHEMA,
        schemas.UNPARTITIONED,
    )
    arrow = pa.table(
        {"cik": [320193], "ticker": ["AAPL"], "title": ["Apple Inc."]},
        schema=schemas.TICKER_MAP_ARROW_SCHEMA,
    )
    appended = writers.append_facts(catalog, schemas.TICKER_MAP_TABLE, arrow)

    assert appended == 1
    table = catalog.load_table(schemas.TICKER_MAP_TABLE)
    assert table.scan().to_arrow().num_rows == 1


@pytest.mark.integration
def test_append_empty_is_noop(tmp_path: Path) -> None:
    catalog = build_catalog(_local_settings(tmp_path))
    ensure_namespace(catalog)
    writers.create_table_if_absent(
        catalog, schemas.TICKER_MAP_TABLE, schemas.TICKER_MAP_SCHEMA, schemas.UNPARTITIONED
    )

    empty = pa.table({"cik": [], "ticker": [], "title": []}, schema=schemas.TICKER_MAP_ARROW_SCHEMA)
    assert writers.append_facts(catalog, schemas.TICKER_MAP_TABLE, empty) == 0


@pytest.mark.integration
def test_schema_evolution_adds_new_column(tmp_path: Path) -> None:
    catalog = build_catalog(_local_settings(tmp_path))
    ensure_namespace(catalog)
    writers.create_table_if_absent(
        catalog, schemas.TICKER_MAP_TABLE, schemas.TICKER_MAP_SCHEMA, schemas.UNPARTITIONED
    )

    # A payload carrying an extra column should evolve the table, not fail.
    # Required columns stay non-nullable (pyiceberg rejects a nullable Arrow
    # field against a required Iceberg field); the new column is optional.
    evolved = pa.table(
        {
            "cik": [789019],
            "ticker": ["MSFT"],
            "title": ["Microsoft Corp"],
            "exchange": ["Nasdaq"],
        },
        schema=pa.schema(
            [
                pa.field("cik", pa.int64(), nullable=False),
                pa.field("ticker", pa.string(), nullable=False),
                pa.field("title", pa.string(), nullable=False),
                pa.field("exchange", pa.string(), nullable=True),
            ]
        ),
    )
    writers.append_facts(catalog, schemas.TICKER_MAP_TABLE, evolved, evolve=True)

    table = catalog.load_table(schemas.TICKER_MAP_TABLE)
    assert "exchange" in {field.name for field in table.schema().fields}
    rows = table.scan().to_arrow().to_pylist()
    assert rows[0]["exchange"] == "Nasdaq"
