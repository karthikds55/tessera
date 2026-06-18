"""The Iceberg bronze write path: create, evolve, and append.

Tables are created on first write and **evolved** when an incoming Arrow table
carries a column the table has not seen yet (rather than failing the append).
The Arrow tables themselves are built upstream by
:mod:`tessera.lakehouse.landing` from dlt's DuckDB output. The Iceberg write
path is the durable contract; the DuckDB read side
(:mod:`tessera.warehouse.duckdb_io`) is best-effort over it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pyarrow as pa
from pyiceberg.exceptions import NoSuchTableError
from pyiceberg.types import (
    BooleanType,
    DateType,
    DoubleType,
    IcebergType,
    IntegerType,
    LongType,
    StringType,
)

from tessera.errors import WarehouseError
from tessera.logging import get_logger

if TYPE_CHECKING:
    from tessera.lakehouse.catalog import Catalog

_log = get_logger("tessera.lakehouse.writers")

# Map pyarrow types to Iceberg types for schema evolution (add_column).
_ARROW_TO_ICEBERG: dict[Any, IcebergType] = {
    pa.int64(): LongType(),
    pa.int32(): IntegerType(),
    pa.float64(): DoubleType(),
    pa.string(): StringType(),
    pa.date32(): DateType(),
    pa.bool_(): BooleanType(),
}


def create_table_if_absent(
    catalog: Catalog, identifier: str, schema: Any, partition_spec: Any
) -> Any:
    """Load ``identifier`` if it exists, otherwise create it.

    Args:
        catalog: The Iceberg catalog.
        identifier: Fully-qualified table identifier (e.g. ``bronze.company_facts``).
        schema: The pyiceberg ``Schema`` for a newly created table.
        partition_spec: The pyiceberg ``PartitionSpec`` for a newly created table.

    Returns:
        The existing or newly created pyiceberg table.
    """
    try:
        return catalog.load_table(identifier)
    except NoSuchTableError:
        table = catalog.create_table(identifier, schema=schema, partition_spec=partition_spec)
        _log.info("table_created", table=identifier)
        return table


def _iceberg_type_for(arrow_type: pa.DataType) -> IcebergType:
    """Return the Iceberg type for an Arrow type, for schema evolution.

    Raises:
        WarehouseError: If the Arrow type has no supported Iceberg mapping.
    """
    iceberg_type = _ARROW_TO_ICEBERG.get(arrow_type)
    if iceberg_type is None:
        raise WarehouseError(f"no Iceberg type mapping for Arrow type {arrow_type}")
    return iceberg_type


def _evolve_to_arrow(table: Any, arrow_table: pa.Table, identifier: str) -> Any:
    """Add any Arrow columns missing from the table schema, then reload.

    Demonstrates additive schema evolution: a payload that introduces a new
    column evolves the Iceberg table instead of failing the append. Existing
    columns are never retyped or dropped here.

    Args:
        table: The pyiceberg table to evolve.
        arrow_table: The incoming Arrow table whose columns drive evolution.
        identifier: Table identifier, for logging and reload.

    Returns:
        The (possibly reloaded) table with all incoming columns present.
    """
    existing = {field.name for field in table.schema().fields}
    new_fields = [f for f in arrow_table.schema if f.name not in existing]
    if not new_fields:
        return table
    with table.update_schema() as update:
        for field in new_fields:
            update.add_column(field.name, _iceberg_type_for(field.type))
            _log.info("schema_evolved", table=identifier, column=field.name, type=str(field.type))
    return table.refresh()


def append_facts(
    catalog: Catalog, identifier: str, arrow_table: pa.Table, *, evolve: bool = True
) -> int:
    """Append an Arrow table to an Iceberg bronze table, evolving schema if needed.

    Despite the name, this is the generic bronze append used by every table; the
    facts table is just the highest-volume caller.

    Args:
        catalog: The Iceberg catalog.
        identifier: The target table identifier.
        arrow_table: The rows to append.
        evolve: When ``True``, add columns present in ``arrow_table`` but absent
            from the table before appending.

    Returns:
        The number of rows appended.
    """
    if arrow_table.num_rows == 0:
        _log.info("append_skipped_empty", table=identifier)
        return 0
    table = catalog.load_table(identifier)
    if evolve:
        table = _evolve_to_arrow(table, arrow_table, identifier)
    table.append(arrow_table)
    _log.info("facts_appended", table=identifier, rows=arrow_table.num_rows)
    return int(arrow_table.num_rows)
