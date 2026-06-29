"""Typed, Streamlit-free query functions over the fundamentals marts.

All screener SQL lives here so the UI layer stays thin and every query is
unit-testable against a tiny in-memory DuckDB fixture. Each function takes an
open DuckDB connection (the app supplies one from
:func:`tessera.warehouse.duckdb_io.connect`) and returns plain Python or a
``pandas`` frame — never a Streamlit object.

The marts live in DuckDB's ``main_marts`` schema (dbt profile base schema
``main`` + the ``marts`` custom schema). Metric names that are interpolated into
SQL as identifiers are validated against :data:`METRICS` first, so a caller can
never inject arbitrary SQL through the ``metric`` argument.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb
    import pandas as pd

# Fully-qualified mart relations.
MART = "main_marts.mart_fundamentals_annual"
DIM = "main_marts.dim_company"

# Whitelisted rankable/plottable metric columns -> human-friendly label. Also the
# allow-list that guards identifier interpolation in screen()/metric_timeseries().
METRICS: dict[str, str] = {
    "revenue": "Revenue",
    "net_income": "Net income",
    "total_assets": "Total assets",
    "total_equity": "Total equity",
    "total_liabilities": "Total liabilities",
    "net_margin": "Net margin",
    "roa": "Return on assets",
    "roe": "Return on equity",
    "debt_to_equity": "Debt / equity",
    "revenue_growth_yoy": "Revenue growth YoY",
}


def _validate_metric(metric: str) -> str:
    """Return ``metric`` if it is a known column, else raise ``ValueError``.

    Args:
        metric: The candidate metric column name.

    Returns:
        The validated metric name, safe to interpolate as a SQL identifier.

    Raises:
        ValueError: If ``metric`` is not in :data:`METRICS`.
    """
    if metric not in METRICS:
        valid = ", ".join(sorted(METRICS))
        raise ValueError(f"unknown metric {metric!r}; valid metrics: {valid}")
    return metric


def marts_available(conn: duckdb.DuckDBPyConnection) -> bool:
    """Return whether the fundamentals mart table exists in the warehouse.

    Args:
        conn: An open DuckDB connection to the warehouse.

    Returns:
        ``True`` if ``main_marts.mart_fundamentals_annual`` is present.
    """
    row = conn.execute(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema = 'main_marts' AND table_name = 'mart_fundamentals_annual'"
    ).fetchone()
    return bool(row and row[0])


def load_industries(conn: duckdb.DuckDBPyConnection) -> list[str]:
    """Return the distinct, non-null industries present in the mart, sorted.

    Args:
        conn: An open DuckDB connection to the warehouse.

    Returns:
        Industry names in ascending order.
    """
    rows = conn.execute(
        f"SELECT DISTINCT industry FROM {MART} WHERE industry IS NOT NULL ORDER BY industry"
    ).fetchall()
    return [str(row[0]) for row in rows]


def available_fiscal_years(conn: duckdb.DuckDBPyConnection) -> list[int]:
    """Return the fiscal years present in the mart, newest first.

    Args:
        conn: An open DuckDB connection to the warehouse.

    Returns:
        Fiscal years in descending order.
    """
    rows = conn.execute(
        f"SELECT DISTINCT fiscal_year FROM {MART} WHERE fiscal_year IS NOT NULL "
        "ORDER BY fiscal_year DESC"
    ).fetchall()
    return [int(row[0]) for row in rows]


def list_companies(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Return current companies (cik, ticker, name) for the company picker.

    Args:
        conn: An open DuckDB connection to the warehouse.

    Returns:
        A frame of the current ``dim_company`` rows, ordered by ticker.
    """
    return conn.execute(
        f"SELECT cik, ticker, name FROM {DIM} WHERE is_current ORDER BY ticker"
    ).df()


def screen(
    conn: duckdb.DuckDBPyConnection,
    *,
    metric: str = "revenue",
    industry: str | None = None,
    fiscal_year: int | None = None,
    limit: int = 50,
    ascending: bool = False,
) -> pd.DataFrame:
    """Rank companies by ``metric`` for a fiscal year, optionally within an industry.

    Args:
        conn: An open DuckDB connection to the warehouse.
        metric: The column to rank by; must be a key of :data:`METRICS`.
        industry: If given, restrict to this industry.
        fiscal_year: If given, restrict to this fiscal year.
        limit: Maximum number of rows to return.
        ascending: Rank ascending (worst-first) instead of descending.

    Returns:
        A frame of the top companies with the headline metrics and the ranked
        metric exposed as ``rank_metric``.

    Raises:
        ValueError: If ``metric`` is not a known column.
    """
    metric = _validate_metric(metric)
    clauses = [f"{metric} IS NOT NULL"]
    params: list[object] = []
    if industry is not None:
        clauses.append("industry = ?")
        params.append(industry)
    if fiscal_year is not None:
        clauses.append("fiscal_year = ?")
        params.append(fiscal_year)
    order = "ASC" if ascending else "DESC"
    params.append(limit)
    sql = f"""
        SELECT ticker, name, industry, fiscal_year,
               revenue, net_income, net_margin, roe, debt_to_equity, revenue_growth_yoy,
               {metric} AS rank_metric
        FROM {MART}
        WHERE {" AND ".join(clauses)}
        ORDER BY {metric} {order} NULLS LAST
        LIMIT ?
    """
    return conn.execute(sql, params).df()


def metric_timeseries(
    conn: duckdb.DuckDBPyConnection, cik: int, metric: str = "revenue"
) -> pd.DataFrame:
    """Return one company's ``metric`` over time, ordered by fiscal year.

    Args:
        conn: An open DuckDB connection to the warehouse.
        cik: The company's Central Index Key.
        metric: The column to plot; must be a key of :data:`METRICS`.

    Returns:
        A frame of ``(fiscal_year, value)`` rows.

    Raises:
        ValueError: If ``metric`` is not a known column.
    """
    metric = _validate_metric(metric)
    sql = f"""
        SELECT fiscal_year, {metric} AS value
        FROM {MART}
        WHERE cik = ?
        ORDER BY fiscal_year
    """
    return conn.execute(sql, [cik]).df()


def peer_comparison(
    conn: duckdb.DuckDBPyConnection, cik: int, fiscal_year: int | None = None
) -> pd.DataFrame:
    """Return same-industry peers of ``cik`` for a fiscal year, ranked by revenue.

    Args:
        conn: An open DuckDB connection to the warehouse.
        cik: The reference company's Central Index Key (its industry defines the peer set).
        fiscal_year: The year to compare in; defaults to the company's latest year.

    Returns:
        A frame of peer companies with headline metrics for the chosen year.
    """
    sql = f"""
        WITH target AS (
            SELECT industry, max(fiscal_year) AS latest_year
            FROM {MART}
            WHERE cik = ?
            GROUP BY industry
        )
        SELECT m.ticker, m.name, m.fiscal_year,
               m.revenue, m.net_margin, m.roe, m.debt_to_equity
        FROM {MART} m
        JOIN target t ON m.industry = t.industry
        WHERE m.fiscal_year = COALESCE(?, t.latest_year)
        ORDER BY m.revenue DESC NULLS LAST
    """
    return conn.execute(sql, [cik, fiscal_year]).df()
