"""Guardrails on the dbt ``concept_map.csv`` seed.

The seed is the single source of normalization truth that the dbt models join
against; :mod:`tessera.ingestion.concepts` is the in-code mirror used elsewhere.
These tests keep the two in lockstep so a tag can never be referenced in code
but silently missing from the seed (or mapped to a different concept).
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from tessera.ingestion.concepts import (
    STANDARD_CONCEPTS,
    all_candidate_tags,
    concept_for_tag,
)

_SEED_PATH = Path(__file__).resolve().parents[1] / "dbt" / "edgar" / "seeds" / "concept_map.csv"
_REQUIRED_COLUMNS = {"raw_tag", "taxonomy", "standard_concept", "sign", "notes"}


def _load_seed() -> list[dict[str, str]]:
    """Return the concept_map seed rows as dicts."""
    with _SEED_PATH.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def seed_rows() -> list[dict[str, str]]:
    """Load the seed once per module."""
    rows = _load_seed()
    assert rows, "concept_map.csv must not be empty"
    return rows


def test_seed_has_required_columns(seed_rows: list[dict[str, str]]) -> None:
    assert _REQUIRED_COLUMNS <= set(seed_rows[0])


def test_seed_covers_every_candidate_tag(seed_rows: list[dict[str, str]]) -> None:
    """Every tag in concepts.py is present in the seed with the same concept."""
    mapped = {row["raw_tag"]: row["standard_concept"] for row in seed_rows}
    for tag in all_candidate_tags():
        assert tag in mapped, f"{tag} missing from concept_map.csv"
        assert mapped[tag] == concept_for_tag(tag), f"{tag} maps to the wrong concept"


def test_seed_concepts_are_known(seed_rows: list[dict[str, str]]) -> None:
    """No seed row introduces a standard_concept that code does not know about."""
    valid = set(STANDARD_CONCEPTS)
    for row in seed_rows:
        assert row["standard_concept"] in valid, f"unknown concept {row['standard_concept']!r}"


def test_seed_signs_are_valid(seed_rows: list[dict[str, str]]) -> None:
    """``sign`` is always -1 or +1 so ``value * sign`` is well-defined."""
    for row in seed_rows:
        assert int(row["sign"]) in (-1, 1), f"bad sign for {row['raw_tag']}"


def test_candidate_tags_are_positive_sign(seed_rows: list[dict[str, str]]) -> None:
    """The current concept set is naturally positive — guards against an accidental flip."""
    signs = {row["raw_tag"]: int(row["sign"]) for row in seed_rows}
    for tag in all_candidate_tags():
        assert signs[tag] == 1, f"{tag} should carry sign +1"


def test_no_duplicate_raw_tags(seed_rows: list[dict[str, str]]) -> None:
    """Each raw tag maps exactly once, so a join can never fan out."""
    tags = [row["raw_tag"] for row in seed_rows]
    assert len(tags) == len(set(tags)), "duplicate raw_tag in concept_map.csv"
