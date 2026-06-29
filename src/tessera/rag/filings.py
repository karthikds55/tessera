"""Locate and parse SEC filing documents for the RAG layer (interfaces).

Turns an issuer's submissions into narrative text for indexing. The contracts are
fully typed; the parsing bodies are documented ``TODO``\\ s. The module talks to
any SEC client through the :class:`FilingsClient` Protocol rather than importing
the ingestion package, so the RAG layer stays decoupled from the core pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import date

# Filing forms that carry the narrative sections (risk factors, MD&A) we index.
NARRATIVE_FORMS = ("10-K", "10-Q")


@dataclass(frozen=True, slots=True)
class FilingDoc:
    """A single primary filing document located for an issuer.

    Attributes:
        cik: Zero-padded Central Index Key of the issuer.
        accession_number: The filing's accession number.
        form: The filing form type (e.g. ``10-K``).
        document: The primary document filename within the filing.
        url: Absolute URL of the primary document on EDGAR.
        filing_date: The date the filing was filed, if known.
    """

    cik: str
    accession_number: str
    form: str
    document: str
    url: str
    filing_date: date | None = None


@runtime_checkable
class FilingsClient(Protocol):
    """Structural seam over the one SEC-client method this module needs.

    Depending on this Protocol instead of a concrete ``EdgarClient`` keeps the RAG
    layer free of any import from the ingestion package.
    """

    def get_submissions(self, cik: str) -> object:
        """Return the issuer's submissions payload (metadata + recent filings)."""
        ...


def fetch_filing_documents(client: FilingsClient, cik: str) -> list[FilingDoc]:
    """Locate the issuer's 10-K/10-Q primary documents from its submissions.

    Args:
        client: An SEC client satisfying :class:`FilingsClient`.
        cik: The issuer's zero-padded CIK.

    Returns:
        One :class:`FilingDoc` per located 10-K/10-Q primary document.

    Raises:
        NotImplementedError: Until the submissions-index walk is implemented.
    """
    # TODO(rag): call client.get_submissions(cik), iterate filings.recent, keep
    # rows whose form is in NARRATIVE_FORMS, and build each primary-document URL
    # (https://www.sec.gov/Archives/edgar/data/<cik>/<accn-no-dashes>/<document>)
    # into a FilingDoc. Returns the located docs; raises EdgarHTTPError on fetch
    # failure once wired.
    raise NotImplementedError("fetch_filing_documents: submissions-index walk pending")


def extract_narrative_sections(doc: FilingDoc) -> dict[str, str]:
    """Extract the narrative sections (risk factors, MD&A) from a filing document.

    Args:
        doc: The filing document to parse.

    Returns:
        A mapping of section key (e.g. ``"risk_factors"``, ``"mda"``) to plain text.
        Sections absent from the filing are omitted from the map.

    Raises:
        NotImplementedError: Until HTML fetch + section segmentation is implemented.
    """
    # TODO(rag): fetch doc.url, strip the HTML to text, and segment Item 1A (Risk
    # Factors) and Item 7 (MD&A) by their standard headings into the returned map.
    raise NotImplementedError("extract_narrative_sections: HTML section parsing pending")
