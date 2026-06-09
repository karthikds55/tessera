"""Tessera: an open-source SEC fundamentals data engine.

Ingests raw XBRL company facts from SEC EDGAR, normalizes inconsistent concept
tagging into a governed lakehouse (Iceberg bronze -> dbt silver/gold in DuckDB),
and serves a fundamentals screener plus a stretch RAG layer over filing narratives.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
