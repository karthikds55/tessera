"""Ingestion package: SEC EDGAR access, typed payload models, and concept candidates.

This package owns everything between the SEC API and the raw lakehouse: a
rate-limited, retrying HTTP client, pydantic models for every payload shape, the
candidate-tag lists that seed concept normalization, and the price-provider seam.
"""

from __future__ import annotations
