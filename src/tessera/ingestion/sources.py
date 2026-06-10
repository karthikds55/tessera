"""Declarative dlt extract-load sources over the SEC EDGAR client.

:func:`edgar_source` exposes the three EDGAR feeds the lakehouse lands as bronze:

- ``company_facts`` — flattened one-fact-per-row XBRL values, the high-volume feed.
  It carries an incremental cursor on ``filed`` so re-runs only pull facts filed
  after the last seen date, and a composite ``primary_key`` so a re-fetched filing
  upserts rather than duplicates (``write_disposition="merge"``).
- ``submissions`` — issuer metadata and recent-filing history feeding ``dim_company``
  and the RAG filing index; merged on ``cik``.
- ``ticker_map`` — the ticker -> CIK directory, fully refreshed each run
  (``write_disposition="replace"``).

All resources delegate to :class:`~tessera.ingestion.edgar_client.EdgarClient`,
which owns rate limiting and retries; dlt owns state, schema inference, and the
load. The destination (local DuckDB by default) is chosen by the caller — see
:mod:`tessera.ingestion.run`. The hand-off to the Iceberg lakehouse lands in
PR-05, which appends the parquet/DuckDB output dlt produces here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import dlt

from tessera.ingestion.models import flatten_company_facts
from tessera.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Iterator

    from tessera.ingestion.edgar_client import EdgarClient

_log = get_logger("tessera.ingestion.sources")


@dlt.source(name="edgar")  # type: ignore[misc]  # dlt decorator is untyped (Any)
def edgar_source(client: EdgarClient, ciks: list[str]) -> Any:
    """Build the EDGAR dlt source exposing the bronze EL resources.

    Args:
        client: The rate-limited SEC client every resource delegates to.
        ciks: The issuer CIKs to extract (any width; the client zero-pads).

    Returns:
        The three dlt resources (``company_facts``, ``submissions``,
        ``ticker_map``) wired into a single source.
    """

    @dlt.resource(  # type: ignore[misc]  # dlt decorator is untyped (Any)
        name="company_facts",
        write_disposition="merge",
        primary_key=("cik", "taxonomy", "raw_tag", "unit", "accn", "start", "end"),
    )
    def company_facts(
        # dlt requires the incremental cursor as an argument default; it inspects
        # the signature to wire state, so it cannot move into the body (B008).
        filed: Any = dlt.sources.incremental("filed", initial_value=None),  # noqa: B008
    ) -> Iterator[dict[str, Any]]:
        """Yield flattened fact rows for each CIK, newest filings first.

        Args:
            filed: dlt incremental cursor on the ``filed`` date; re-runs resume
                from the last seen value so only newly filed facts are emitted.
        """
        for cik in ciks:
            log = _log.bind(cik=cik)
            log.info("extract_company_facts")
            facts = client.get_company_facts(cik)
            for row in flatten_company_facts(facts):
                yield row.model_dump(mode="json")

    @dlt.resource(  # type: ignore[misc]  # dlt decorator is untyped (Any)
        name="submissions",
        write_disposition="merge",
        primary_key="cik",
    )
    def submissions() -> Iterator[dict[str, Any]]:
        """Yield one filing-history/metadata record per CIK."""
        for cik in ciks:
            log = _log.bind(cik=cik)
            log.info("extract_submissions")
            yield client.get_submissions(cik).model_dump(mode="json")

    @dlt.resource(  # type: ignore[misc]  # dlt decorator is untyped (Any)
        name="ticker_map",
        write_disposition="replace",
    )
    def ticker_map() -> Iterator[dict[str, Any]]:
        """Yield the full ticker -> CIK directory, replacing the prior load."""
        _log.info("extract_ticker_map")
        for entry in client.get_ticker_map():
            yield entry.model_dump(mode="json")

    return company_facts, submissions, ticker_map
