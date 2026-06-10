"""Pydantic models for SEC EDGAR payloads and the flattened fact row.

The models are tolerant of unknown fields (``extra="ignore"``) so additive SEC
changes do not break ingestion, but fail fast (raise ``ValidationError``) when a
required field is missing or mistyped. :func:`flatten_company_facts` turns the
deeply nested companyfacts structure into tidy one-fact-per-row records.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

# Shared model configuration: ignore unknown keys, allow construction by field name.
_MODEL_CONFIG = ConfigDict(extra="ignore", populate_by_name=True)


class ConceptUnitFact(BaseModel):
    """A single reported value for one concept, unit, and period."""

    model_config = _MODEL_CONFIG

    val: float
    accn: str
    start: date | None = None
    end: date | None = None
    fy: int | None = None
    fp: str | None = None
    form: str | None = None
    filed: date | None = None
    frame: str | None = None


class ConceptData(BaseModel):
    """All reported facts for one XBRL concept, grouped by unit of measure."""

    model_config = _MODEL_CONFIG

    label: str | None = None
    description: str | None = None
    units: dict[str, list[ConceptUnitFact]]


class CompanyFacts(BaseModel):
    """The full ``companyfacts`` payload for a single issuer.

    ``facts`` is keyed first by taxonomy (e.g. ``us-gaap``, ``dei``) and then by
    raw XBRL tag.
    """

    model_config = _MODEL_CONFIG

    cik: int
    entity_name: str = Field(alias="entityName")
    facts: dict[str, dict[str, ConceptData]]


class CompanyConcept(BaseModel):
    """The ``companyconcept`` payload: one tag's full history for one issuer."""

    model_config = _MODEL_CONFIG

    cik: int
    taxonomy: str
    tag: str
    entity_name: str = Field(alias="entityName")
    units: dict[str, list[ConceptUnitFact]]


class FrameFact(BaseModel):
    """One issuer's value for a tag within a single reporting frame."""

    model_config = _MODEL_CONFIG

    accn: str
    cik: int
    entity_name: str = Field(alias="entityName")
    start: date | None = None
    end: date | None = None
    val: float


class FrameResponse(BaseModel):
    """The ``frames`` payload: one tag across all issuers for one period."""

    model_config = _MODEL_CONFIG

    taxonomy: str
    tag: str
    ccp: str
    uom: str
    label: str | None = None
    pts: int | None = None
    data: list[FrameFact]


class RecentFilings(BaseModel):
    """Parallel arrays describing an issuer's most recent filings."""

    model_config = _MODEL_CONFIG

    accession_number: list[str] = Field(alias="accessionNumber", default_factory=list)
    form: list[str] = Field(default_factory=list)
    filing_date: list[date] = Field(alias="filingDate", default_factory=list)
    primary_document: list[str] = Field(alias="primaryDocument", default_factory=list)
    primary_doc_description: list[str] = Field(alias="primaryDocDescription", default_factory=list)


class FilingsIndex(BaseModel):
    """Container for an issuer's filing history (recent block plus paged files)."""

    model_config = _MODEL_CONFIG

    recent: RecentFilings = Field(default_factory=RecentFilings)


class Submissions(BaseModel):
    """The ``submissions`` payload: issuer metadata and filing history."""

    model_config = _MODEL_CONFIG

    cik: str
    name: str
    tickers: list[str] = Field(default_factory=list)
    exchanges: list[str] = Field(default_factory=list)
    sic: str | None = None
    sic_description: str | None = Field(alias="sicDescription", default=None)
    state_of_incorporation: str | None = Field(alias="stateOfIncorporation", default=None)
    fiscal_year_end: str | None = Field(alias="fiscalYearEnd", default=None)
    filings: FilingsIndex = Field(default_factory=FilingsIndex)


class TickerMapEntry(BaseModel):
    """One row of the ticker -> CIK map (``company_tickers.json``)."""

    model_config = _MODEL_CONFIG

    cik: int = Field(alias="cik_str")
    ticker: str
    title: str


class FactRow(BaseModel):
    """A single flattened fact: the grain of the bronze fact table."""

    cik: int
    taxonomy: str
    raw_tag: str
    unit: str
    value: float
    fy: int | None
    fp: str | None
    form: str | None
    frame: str | None
    accn: str
    start: date | None
    end: date | None
    filed: date | None


def flatten_company_facts(facts: CompanyFacts) -> list[FactRow]:
    """Flatten a :class:`CompanyFacts` payload into tidy fact rows.

    Args:
        facts: The parsed companyfacts payload for one issuer.

    Returns:
        One :class:`FactRow` per reported value across every taxonomy, tag, and unit.
    """
    rows: list[FactRow] = []
    for taxonomy, tags in facts.facts.items():
        for raw_tag, concept_data in tags.items():
            for unit, unit_facts in concept_data.units.items():
                rows.extend(
                    FactRow(
                        cik=facts.cik,
                        taxonomy=taxonomy,
                        raw_tag=raw_tag,
                        unit=unit,
                        value=fact.val,
                        fy=fact.fy,
                        fp=fact.fp,
                        form=fact.form,
                        frame=fact.frame,
                        accn=fact.accn,
                        start=fact.start,
                        end=fact.end,
                        filed=fact.filed,
                    )
                    for fact in unit_facts
                )
    return rows
