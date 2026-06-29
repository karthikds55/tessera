"""Tests for the RAG interface stubs.

Exercise the one piece with real logic (``chunk_text``), confirm the skeleton
implementations satisfy their Protocols, and assert the documented stub bodies
raise ``NotImplementedError`` (and the answer guard raises ``ConfigError``)
rather than silently passing. Imports here also prove ``tessera.rag`` loads
without the ``rag`` extra installed.
"""

from __future__ import annotations

import pytest

from tessera.config import Settings
from tessera.errors import ConfigError
from tessera.rag import (
    Chunk,
    Embedder,
    FilingDoc,
    LanceDBStore,
    PgVectorStore,
    Retriever,
    SentenceTransformerEmbedder,
    VectorStore,
    chunk_text,
    embed_and_store,
    extract_narrative_sections,
    fetch_filing_documents,
)


def test_chunk_text_splits_into_windows() -> None:
    chunks = chunk_text("a b c d e", max_tokens=2)
    assert [c.text for c in chunks] == ["a b", "c d", "e"]
    assert [c.index for c in chunks] == [0, 1, 2]


def test_chunk_text_whitespace_yields_no_chunks() -> None:
    assert chunk_text("   ", max_tokens=10) == []


def test_chunk_text_single_chunk_when_under_limit() -> None:
    chunks = chunk_text("hello world", max_tokens=50)
    assert len(chunks) == 1
    assert chunks[0] == Chunk(text="hello world", index=0)


def test_chunk_text_rejects_nonpositive_max_tokens() -> None:
    with pytest.raises(ValueError, match="max_tokens"):
        chunk_text("x", max_tokens=0)


def test_skeletons_satisfy_protocols() -> None:
    assert isinstance(SentenceTransformerEmbedder(), Embedder)
    assert isinstance(LanceDBStore(), VectorStore)
    assert isinstance(PgVectorStore(dsn="postgresql://localhost/tessera"), VectorStore)


def test_stub_bodies_raise_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        SentenceTransformerEmbedder().embed(["hello"])
    with pytest.raises(NotImplementedError):
        LanceDBStore().add([Chunk(text="x", index=0)], [[0.0]])
    with pytest.raises(NotImplementedError):
        embed_and_store(
            [Chunk(text="x", index=0)], SentenceTransformerEmbedder(), LanceDBStore()
        )
    with pytest.raises(NotImplementedError):
        extract_narrative_sections(
            FilingDoc(
                cik="0000320193",
                accession_number="0000320193-23-000106",
                form="10-K",
                document="aapl-20230930.htm",
                url="https://example.test/doc.htm",
            )
        )


def test_fetch_filing_documents_is_stub() -> None:
    class _Client:
        def get_submissions(self, cik: str) -> object:
            return {}

    with pytest.raises(NotImplementedError):
        fetch_filing_documents(_Client(), "0000320193")


def test_retriever_answer_requires_api_key() -> None:
    retriever = Retriever(
        SentenceTransformerEmbedder(),
        LanceDBStore(),
        settings=Settings(anthropic_api_key=None),
    )
    with pytest.raises(ConfigError):
        retriever.answer("What are the risk factors?")
