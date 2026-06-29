"""Stretch-goal RAG-over-filings layer for tessera (interfaces + stubs).

Fully typed, documented interfaces decoupled from the core pipeline behind
:class:`typing.Protocol` seams, with explicit ``TODO`` bodies rather than empty
contracts. The heavy optional dependencies (``sentence-transformers``,
``lancedb``, ``psycopg``, ``anthropic``) are referenced only inside ``TODO``
comments, so ``import tessera.rag`` — and the core package — works without the
``rag`` extra installed.
"""

from __future__ import annotations

from tessera.rag.chunk_embed import (
    Chunk,
    Embedder,
    Embedding,
    LanceDBStore,
    PgVectorStore,
    SentenceTransformerEmbedder,
    VectorStore,
    chunk_text,
    embed_and_store,
)
from tessera.rag.filings import (
    NARRATIVE_FORMS,
    FilingDoc,
    FilingsClient,
    extract_narrative_sections,
    fetch_filing_documents,
)
from tessera.rag.retriever import DEFAULT_ANSWER_MODEL, Retriever

__all__ = [
    "DEFAULT_ANSWER_MODEL",
    "NARRATIVE_FORMS",
    "Chunk",
    "Embedder",
    "Embedding",
    "FilingDoc",
    "FilingsClient",
    "LanceDBStore",
    "PgVectorStore",
    "Retriever",
    "SentenceTransformerEmbedder",
    "VectorStore",
    "chunk_text",
    "embed_and_store",
    "extract_narrative_sections",
    "fetch_filing_documents",
]
