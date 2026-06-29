"""Smoke tests for the Dagster :class:`Definitions` object.

These assert the orchestration loads and wires together without touching any
external engine — they validate the asset graph, checks, schedule, and sensor
are registered, not that a run succeeds.
"""

from __future__ import annotations

from orchestration.definitions import (
    dbt_models,
    defs,
    fact_referential_integrity,
    fundamentals_are_fresh,
    fundamentals_mart,
    iceberg_bronze,
    mart_grain_is_unique,
    net_margin_within_bounds,
    new_filings_sensor,
    raw_companyfacts,
    ticker_universe,
    weekly_refresh_schedule,
)

_EXPECTED_CHECKS = {
    "mart_grain_is_unique",
    "fact_referential_integrity",
    "net_margin_within_bounds",
    "fundamentals_are_fresh",
}


def test_definitions_resolve() -> None:
    """Building the repository forces Dagster to validate the whole graph."""
    # Raises if any asset/check/job/schedule/sensor is mis-wired.
    assert defs.get_repository_def() is not None


def test_all_assets_present() -> None:
    """Every expected asset key is registered."""
    keys = {
        a.key.to_user_string()
        for a in (
            ticker_universe,
            raw_companyfacts,
            iceberg_bronze,
            dbt_models,
            fundamentals_mart,
        )
    }
    assert keys == {
        "ticker_universe",
        "raw_companyfacts",
        "iceberg_bronze",
        "dbt_models",
        "fundamentals_mart",
    }


def test_asset_graph_wiring() -> None:
    """The graph is chained ticker_universe → ... → fundamentals_mart."""
    assert raw_companyfacts.dependency_keys == {ticker_universe.key}
    assert iceberg_bronze.dependency_keys == {raw_companyfacts.key}
    assert dbt_models.dependency_keys == {iceberg_bronze.key}
    assert fundamentals_mart.dependency_keys == {dbt_models.key}


def test_upstream_assets_are_partitioned() -> None:
    """Extract assets carry the fiscal-year partition; transform assets do not."""
    assert raw_companyfacts.partitions_def is not None
    assert iceberg_bronze.partitions_def is not None
    assert dbt_models.partitions_def is None


def test_asset_checks_registered() -> None:
    """All four data-quality asset checks are present and target the mart."""
    checks = (
        mart_grain_is_unique,
        fact_referential_integrity,
        net_margin_within_bounds,
        fundamentals_are_fresh,
    )
    names = {key.name for check in checks for key in check.check_keys}
    assert names == _EXPECTED_CHECKS
    # Every check targets the fundamentals_mart asset.
    targets = {key.asset_key for check in checks for key in check.check_keys}
    assert targets == {fundamentals_mart.key}


def test_schedule_and_sensor_registered() -> None:
    """The refresh schedule and new-filings sensor are wired in."""
    assert weekly_refresh_schedule.name == "weekly_mart_refresh"
    assert new_filings_sensor.name == "new_filings_sensor"
