"""Iceberg and Arrow schema definitions for the bronze tables.

Three bronze tables land raw SEC data:

- ``bronze.company_facts`` — the flattened one-fact-per-row XBRL grain
  (mirrors :class:`~tessera.ingestion.models.FactRow`).
- ``bronze.submissions`` — one metadata row per issuer for ``dim_company``.
- ``bronze.ticker_map`` — the ticker -> CIK directory.

Each table has a paired pyarrow schema whose field nullability matches the
Iceberg ``required``/``optional`` flags exactly: pyiceberg validates the two on
append and rejects a nullable Arrow field against a required Iceberg field.

**Partitioning choice (company_facts):** identity on ``fiscal_year`` (``fy``).
We deliberately avoid a ``bucket`` transform on ``raw_tag`` — bucketing requires
the optional ``pyiceberg-core`` Rust extension, which is not part of the local
profile. Identity-on-``fy`` keeps the local stack dependency-light and prunes
the typical fiscal-year-ranged scans dbt issues over the facts table.
"""

from __future__ import annotations

import pyarrow as pa
from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.transforms import IdentityTransform
from pyiceberg.types import (
    DateType,
    DoubleType,
    IntegerType,
    LongType,
    NestedField,
    StringType,
)

# --- bronze.company_facts ----------------------------------------------------
COMPANY_FACTS_TABLE = "bronze.company_facts"

COMPANY_FACTS_SCHEMA = Schema(
    NestedField(1, "cik", LongType(), required=True),
    NestedField(2, "taxonomy", StringType(), required=True),
    NestedField(3, "raw_tag", StringType(), required=True),
    NestedField(4, "unit", StringType(), required=True),
    NestedField(5, "value", DoubleType(), required=True),
    NestedField(6, "fy", IntegerType(), required=False),
    NestedField(7, "fp", StringType(), required=False),
    NestedField(8, "form", StringType(), required=False),
    NestedField(9, "frame", StringType(), required=False),
    NestedField(10, "accn", StringType(), required=True),
    NestedField(11, "start", DateType(), required=False),
    NestedField(12, "end", DateType(), required=False),
    NestedField(13, "filed", DateType(), required=False),
)

# Identity partition on fiscal year (see module docstring for the rationale).
COMPANY_FACTS_PARTITION_SPEC = PartitionSpec(
    PartitionField(source_id=6, field_id=1000, transform=IdentityTransform(), name="fy")
)

COMPANY_FACTS_ARROW_SCHEMA = pa.schema(
    [
        pa.field("cik", pa.int64(), nullable=False),
        pa.field("taxonomy", pa.string(), nullable=False),
        pa.field("raw_tag", pa.string(), nullable=False),
        pa.field("unit", pa.string(), nullable=False),
        pa.field("value", pa.float64(), nullable=False),
        pa.field("fy", pa.int32(), nullable=True),
        pa.field("fp", pa.string(), nullable=True),
        pa.field("form", pa.string(), nullable=True),
        pa.field("frame", pa.string(), nullable=True),
        pa.field("accn", pa.string(), nullable=False),
        pa.field("start", pa.date32(), nullable=True),
        pa.field("end", pa.date32(), nullable=True),
        pa.field("filed", pa.date32(), nullable=True),
    ]
)

# --- bronze.submissions ------------------------------------------------------
SUBMISSIONS_TABLE = "bronze.submissions"

SUBMISSIONS_SCHEMA = Schema(
    NestedField(1, "cik", StringType(), required=True),
    NestedField(2, "name", StringType(), required=True),
    NestedField(3, "tickers", StringType(), required=False),
    NestedField(4, "exchanges", StringType(), required=False),
    NestedField(5, "sic", StringType(), required=False),
    NestedField(6, "sic_description", StringType(), required=False),
    NestedField(7, "state_of_incorporation", StringType(), required=False),
    NestedField(8, "fiscal_year_end", StringType(), required=False),
)

SUBMISSIONS_ARROW_SCHEMA = pa.schema(
    [
        pa.field("cik", pa.string(), nullable=False),
        pa.field("name", pa.string(), nullable=False),
        pa.field("tickers", pa.string(), nullable=True),
        pa.field("exchanges", pa.string(), nullable=True),
        pa.field("sic", pa.string(), nullable=True),
        pa.field("sic_description", pa.string(), nullable=True),
        pa.field("state_of_incorporation", pa.string(), nullable=True),
        pa.field("fiscal_year_end", pa.string(), nullable=True),
    ]
)

# --- bronze.ticker_map -------------------------------------------------------
TICKER_MAP_TABLE = "bronze.ticker_map"

TICKER_MAP_SCHEMA = Schema(
    NestedField(1, "cik", LongType(), required=True),
    NestedField(2, "ticker", StringType(), required=True),
    NestedField(3, "title", StringType(), required=True),
)

TICKER_MAP_ARROW_SCHEMA = pa.schema(
    [
        pa.field("cik", pa.int64(), nullable=False),
        pa.field("ticker", pa.string(), nullable=False),
        pa.field("title", pa.string(), nullable=False),
    ]
)

# Unpartitioned spec shared by the small dimension-like bronze tables.
UNPARTITIONED = PartitionSpec()
