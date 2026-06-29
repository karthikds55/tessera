"""Streamlit fundamentals screener UI.

A thin presentation layer over :mod:`dashboard.queries`: it opens a DuckDB
connection from :class:`~tessera.config.Settings` (never a hardcoded path),
caches query results, and renders the screener, peer table, and a metric
time-series chart. All SQL lives in :mod:`dashboard.queries`.

Run with ``inv dashboard`` (``streamlit run dashboard/app.py``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import streamlit as st

from dashboard import queries
from tessera.config import get_settings
from tessera.warehouse.duckdb_io import connect

if TYPE_CHECKING:
    import duckdb
    import pandas as pd


@st.cache_resource
def _get_connection() -> duckdb.DuckDBPyConnection:
    """Open (once per session) the warehouse connection from settings."""
    return connect(get_settings())


# The leading underscore tells Streamlit not to hash the connection argument;
# the remaining args form the cache key.
@st.cache_data(show_spinner=False)
def _industries(_conn: duckdb.DuckDBPyConnection) -> list[str]:
    """Cached distinct industries."""
    return queries.load_industries(_conn)


@st.cache_data(show_spinner=False)
def _fiscal_years(_conn: duckdb.DuckDBPyConnection) -> list[int]:
    """Cached fiscal years (newest first)."""
    return queries.available_fiscal_years(_conn)


@st.cache_data(show_spinner=False)
def _companies(_conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Cached company picker frame."""
    return queries.list_companies(_conn)


@st.cache_data(show_spinner=False)
def _screen(
    _conn: duckdb.DuckDBPyConnection,
    metric: str,
    industry: str | None,
    fiscal_year: int | None,
    limit: int,
    ascending: bool,
) -> pd.DataFrame:
    """Cached screen results."""
    return queries.screen(
        _conn,
        metric=metric,
        industry=industry,
        fiscal_year=fiscal_year,
        limit=limit,
        ascending=ascending,
    )


@st.cache_data(show_spinner=False)
def _timeseries(_conn: duckdb.DuckDBPyConnection, cik: int, metric: str) -> pd.DataFrame:
    """Cached metric time-series for one company."""
    return queries.metric_timeseries(_conn, cik, metric)


@st.cache_data(show_spinner=False)
def _peers(_conn: duckdb.DuckDBPyConnection, cik: int, fiscal_year: int | None) -> pd.DataFrame:
    """Cached peer-comparison frame."""
    return queries.peer_comparison(_conn, cik, fiscal_year)


def _render_screener(conn: duckdb.DuckDBPyConnection) -> None:
    """Render the sidebar controls and the ranked screener table."""
    st.subheader("Screener")
    industries = _industries(conn)
    years = _fiscal_years(conn)

    with st.sidebar:
        st.header("Filters")
        metric = st.selectbox(
            "Rank by",
            options=list(queries.METRICS),
            format_func=lambda key: queries.METRICS[key],
        )
        industry = st.selectbox("Industry", options=["All", *industries])
        fiscal_year = st.selectbox("Fiscal year", options=years) if years else None
        limit = st.slider("Max companies", min_value=5, max_value=100, value=25, step=5)
        ascending = st.toggle("Worst first", value=False)

    results = _screen(
        conn,
        metric=metric,
        industry=None if industry == "All" else industry,
        fiscal_year=fiscal_year,
        limit=limit,
        ascending=ascending,
    )
    st.caption(f"{len(results)} companies ranked by {queries.METRICS[metric]}.")
    st.dataframe(results, use_container_width=True, hide_index=True)


def _render_company_detail(conn: duckdb.DuckDBPyConnection) -> None:
    """Render the per-company metric time series and the peer-comparison table."""
    st.subheader("Company detail")
    companies = _companies(conn)
    if companies.empty:
        st.info("No companies available yet.")
        return

    labels = {
        int(row.cik): f"{row.ticker} — {row.name}" for row in companies.itertuples(index=False)
    }
    cik = st.selectbox(
        "Company", options=list(labels), format_func=lambda value: labels[value]
    )
    metric = st.selectbox(
        "Metric",
        options=list(queries.METRICS),
        format_func=lambda key: queries.METRICS[key],
        key="detail_metric",
    )

    series = _timeseries(conn, cik, metric)
    if series.empty:
        st.info("No data for this company/metric.")
    else:
        st.line_chart(series, x="fiscal_year", y="value")

    st.markdown("**Industry peers**")
    st.dataframe(_peers(conn, cik, None), use_container_width=True, hide_index=True)


def main() -> None:
    """Entry point: build the page and dispatch to the screener / detail views."""
    st.set_page_config(page_title="Tessera Fundamentals Screener", layout="wide")
    st.title("Tessera — Fundamentals Screener")

    conn = _get_connection()
    if not queries.marts_available(conn):
        st.warning(
            "The fundamentals marts have not been built yet. Run `inv pipeline` "
            "(seed → ingest → dbt build) and refresh this page."
        )
        st.stop()

    screener_tab, detail_tab = st.tabs(["Screener", "Company detail"])
    with screener_tab:
        _render_screener(conn)
    with detail_tab:
        _render_company_detail(conn)


if __name__ == "__main__":
    main()
