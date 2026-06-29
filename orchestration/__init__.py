"""Dagster orchestration for the tessera pipeline.

The :mod:`orchestration.definitions` module models the EDGAR fundamentals
pipeline as software-defined assets with a refresh schedule, a new-filings
sensor, and asset checks that mirror the dbt data-quality rules. Load it with
``dagster dev -f orchestration/definitions.py`` (or ``inv dagster``).
"""

from __future__ import annotations
