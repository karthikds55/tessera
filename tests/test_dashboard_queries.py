"""Offline tests for the screener query layer.

Build a tiny in-memory DuckDB warehouse shaped like the real marts and assert the
``dashboard.queries`` SQL behaves: ranking, filtering, metric validation, and the
empty-warehouse guard. No Streamlit, no network, no built warehouse needed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import duckdb
import pytest

from dashboard import queries

if TYPE_CHECKING:
    from collections.abc import Iterator

# (cik, company_key, ticker, name, industry, fiscal_year, revenue, net_income,
#  total_assets, total_equity, total_liabilities, net_margin, roa, roe,
#  debt_to_equity, revenue_growth_yoy)
_MART_ROWS = [
    (320193, "k1", "AAPL", "Apple Inc.", "Technology", 2022, 394.0, 99.0, 352.0, 50.0, 302.0,
     0.251, 0.281, 1.98, 6.04, None),
    (320193, "k1", "AAPL", "Apple Inc.", "Technology", 2023, 383.0, 97.0, 352.0, 62.0, 290.0,
     0.253, 0.275, 1.56, 4.68, -0.028),
    (789019, "k2", "MSFT", "Microsoft Corp.", "Technology", 2023, 211.0, 72.0, 411.0, 206.0,
     205.0, 0.341, 0.175, 0.349, 0.995, 0.069),
    (1045810, "k3", "NVDA", "NVIDIA Corp.", "Semiconductors", 2023, 60.0, 29.0, 65.0, 42.0, 22.0,
     0.487, 0.453, 0.704, 0.531, 1.255),
]

_DIM_ROWS = [
    (320193, "k1", "AAPL", "Apple Inc.", True),
    (789019, "k2", "MSFT", "Microsoft Corp.", True),
    (1045810, "k3", "NVDA", "NVIDIA Corp.", True),
]


@pytest.fixture
def conn() -> Iterator[duckdb.DuckDBPyConnection]:
    """Yield an in-memory DuckDB seeded with mart-shaped fixtures."""
    connection = duckdb.connect(":memory:")
    connection.execute("CREATE SCHEMA main_marts")
    connection.execute(
        """
        CREATE TABLE main_marts.mart_fundamentals_annual (
            cik BIGINT, company_key VARCHAR, ticker VARCHAR, name VARCHAR, industry VARCHAR,
            fiscal_year INTEGER, revenue DOUBLE, net_income DOUBLE, total_assets DOUBLE,
            total_equity DOUBLE, total_liabilities DOUBLE, net_margin DOUBLE, roa DOUBLE,
            roe DOUBLE, debt_to_equity DOUBLE, revenue_growth_yoy DOUBLE
        )
        """
    )
    connection.execute(
        "CREATE TABLE main_marts.dim_company "
        "(cik BIGINT, company_key VARCHAR, ticker VARCHAR, name VARCHAR, is_current BOOLEAN)"
    )
    connection.executemany(
        "INSERT INTO main_marts.mart_fundamentals_annual VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        _MART_ROWS,
    )
    connection.executemany(
        "INSERT INTO main_marts.dim_company VALUES (?,?,?,?,?)", _DIM_ROWS
    )
    try:
        yield connection
    finally:
        connection.close()


def test_marts_available_true(conn: duckdb.DuckDBPyConnection) -> None:
    assert queries.marts_available(conn) is True


def test_marts_available_false_on_empty_db() -> None:
    empty = duckdb.connect(":memory:")
    try:
        assert queries.marts_available(empty) is False
    finally:
        empty.close()


def test_load_industries_sorted_distinct(conn: duckdb.DuckDBPyConnection) -> None:
    assert queries.load_industries(conn) == ["Semiconductors", "Technology"]


def test_available_fiscal_years_desc(conn: duckdb.DuckDBPyConnection) -> None:
    assert queries.available_fiscal_years(conn) == [2023, 2022]


def test_screen_ranks_by_metric_desc(conn: duckdb.DuckDBPyConnection) -> None:
    # 2023 revenues: AAPL 383, MSFT 211, NVDA 60 -> ranked descending by revenue.
    result = queries.screen(conn, metric="revenue", fiscal_year=2023)
    assert list(result["ticker"]) == ["AAPL", "MSFT", "NVDA"]


def test_screen_filters_by_industry_and_limit(conn: duckdb.DuckDBPyConnection) -> None:
    result = queries.screen(conn, metric="roe", industry="Technology", limit=1)
    assert len(result) == 1
    assert result.iloc[0]["industry"] == "Technology"


def test_screen_ascending(conn: duckdb.DuckDBPyConnection) -> None:
    result = queries.screen(conn, metric="revenue", fiscal_year=2023, ascending=True)
    assert list(result["ticker"])[0] == "NVDA"  # lowest 2023 revenue


def test_screen_rejects_unknown_metric(conn: duckdb.DuckDBPyConnection) -> None:
    with pytest.raises(ValueError, match="unknown metric"):
        queries.screen(conn, metric="ebitda")


def test_metric_timeseries_ordered(conn: duckdb.DuckDBPyConnection) -> None:
    series = queries.metric_timeseries(conn, 320193, "revenue")
    assert list(series["fiscal_year"]) == [2022, 2023]
    assert list(series["value"]) == [394.0, 383.0]


def test_peer_comparison_same_industry(conn: duckdb.DuckDBPyConnection) -> None:
    peers = queries.peer_comparison(conn, 789019, 2023)
    # MSFT's industry is Technology -> AAPL + MSFT in 2023, not NVDA.
    assert set(peers["ticker"]) == {"AAPL", "MSFT"}


def test_list_companies(conn: duckdb.DuckDBPyConnection) -> None:
    companies = queries.list_companies(conn)
    assert list(companies["ticker"]) == ["AAPL", "MSFT", "NVDA"]
