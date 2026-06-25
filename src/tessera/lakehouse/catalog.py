"""Iceberg catalog factory and namespace helpers.

:func:`build_catalog` is the single place a pyiceberg catalog is constructed. The
local profile uses a SQLite-backed ``sql`` catalog over a filesystem warehouse;
the cloud profile uses AWS Glue over S3. Callers depend on the :class:`Catalog`
``Protocol`` seam rather than a concrete pyiceberg class, so the rest of the code
is decoupled from the catalog implementation.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pyiceberg.exceptions import NamespaceAlreadyExistsError

from tessera.errors import CatalogError
from tessera.logging import get_logger

if TYPE_CHECKING:
    from tessera.config import Settings

_log = get_logger("tessera.lakehouse.catalog")

# Catalog name registered with pyiceberg; arbitrary but stable.
CATALOG_NAME = "tessera"
# The namespace all bronze tables live under.
BRONZE_NAMESPACE = "bronze"


@runtime_checkable
class Catalog(Protocol):
    """Structural seam over the subset of pyiceberg's catalog API we use.

    Depending on this Protocol instead of a concrete catalog class keeps the
    writers and warehouse code independent of whether we are on SQLite or Glue.
    The signatures mirror pyiceberg's (identifiers are ``str | tuple[str, ...]``,
    create methods accept the optional ``properties``/``sort_order`` kwargs) so
    the concrete ``SqlCatalog``/``GlueCatalog`` classes structurally satisfy it.
    """

    def create_namespace(
        self, namespace: str | tuple[str, ...], properties: dict[str, Any] = ...
    ) -> None:
        """Create a namespace, raising if it already exists."""
        ...

    def create_table(
        self,
        identifier: str | tuple[str, ...],
        schema: Any,
        location: str | None = ...,
        partition_spec: Any = ...,
        sort_order: Any = ...,
        properties: dict[str, Any] = ...,
    ) -> Any:
        """Create a table and return the new table object."""
        ...

    def load_table(self, identifier: str | tuple[str, ...]) -> Any:
        """Load and return an existing table object."""
        ...

    def list_tables(self, namespace: str | tuple[str, ...]) -> list[tuple[str, ...]]:
        """List table identifiers within a namespace."""
        ...


def build_catalog(settings: Settings) -> Catalog:
    """Construct the Iceberg catalog for the active deployment profile.

    Args:
        settings: Application settings supplying catalog URI, warehouse path, and
            (in cloud) the S3 bucket.

    Returns:
        A pyiceberg catalog satisfying the :class:`Catalog` Protocol.

    Raises:
        CatalogError: If the catalog cannot be constructed.
    """
    if settings.is_cloud:
        return _build_glue_catalog(settings)
    return _build_sql_catalog(settings)


def _build_sql_catalog(settings: Settings) -> Catalog:
    """Build the local SQLite + filesystem catalog, creating parent dirs as needed."""
    from pyiceberg.catalog.sql import SqlCatalog

    # The SQLite catalog file and the warehouse tree must exist before use.
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    warehouse = Path(settings.iceberg_warehouse).resolve()
    warehouse.mkdir(parents=True, exist_ok=True)
    try:
        catalog = SqlCatalog(
            CATALOG_NAME,
            uri=settings.iceberg_catalog_uri,
            warehouse=f"file://{warehouse.as_posix()}",
        )
    except Exception as exc:  # pyiceberg raises a variety of init-time errors
        raise CatalogError(f"failed to build local SQLite catalog: {exc}") from exc
    _log.info("catalog_built", profile="local", warehouse=str(warehouse))
    return catalog


def _build_glue_catalog(settings: Settings) -> Catalog:
    """Build the cloud Glue catalog over the S3 warehouse (untested locally)."""
    from pyiceberg.catalog.glue import GlueCatalog

    try:
        catalog = GlueCatalog(
            CATALOG_NAME,
            warehouse=f"s3://{settings.s3_bucket}/iceberg",
        )
    except Exception as exc:
        raise CatalogError(f"failed to build Glue catalog: {exc}") from exc
    _log.info("catalog_built", profile="cloud", bucket=settings.s3_bucket)
    return catalog


def ensure_namespace(catalog: Catalog, namespace: str = BRONZE_NAMESPACE) -> None:
    """Create ``namespace`` if it does not already exist (idempotent).

    Args:
        catalog: The Iceberg catalog.
        namespace: The namespace to ensure; defaults to ``bronze``.
    """
    try:
        catalog.create_namespace(namespace)
        _log.info("namespace_created", namespace=namespace)
    except NamespaceAlreadyExistsError:
        _log.debug("namespace_exists", namespace=namespace)
