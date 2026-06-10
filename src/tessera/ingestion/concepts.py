"""Candidate raw-tag lists per standard concept.

This module is the in-code source of truth that the dbt ``concept_map.csv`` seed
mirrors. It documents which raw XBRL tags should roll up to each governed standard
concept, so coverage can be asserted in tests and the seed can be regenerated.
"""

from __future__ import annotations

STANDARD_CONCEPTS: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
    ],
    "total_assets": [
        "Assets",
    ],
    "total_equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "total_liabilities": [
        "Liabilities",
    ],
}
"""Mapping of standard concept name to the raw XBRL tags that roll up to it."""


def all_candidate_tags() -> set[str]:
    """Return the set of every raw tag referenced by any standard concept.

    Returns:
        A set union of all candidate tags across :data:`STANDARD_CONCEPTS`.
    """
    return {tag for tags in STANDARD_CONCEPTS.values() for tag in tags}


def concept_for_tag(raw_tag: str) -> str | None:
    """Return the standard concept a raw tag maps to, or ``None`` if unmapped.

    Args:
        raw_tag: The raw XBRL tag as filed.

    Returns:
        The standard concept name, or ``None`` when the tag is not a candidate.
    """
    for concept, tags in STANDARD_CONCEPTS.items():
        if raw_tag in tags:
            return concept
    return None
