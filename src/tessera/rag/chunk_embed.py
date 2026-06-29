"""Chunking, embedding, and vector-store interfaces for RAG.

:func:`chunk_text` carries the only real logic in this PR. The :class:`Embedder`
and :class:`VectorStore` Protocols define the contracts; the local/cloud skeletons
(:class:`SentenceTransformerEmbedder`, :class:`LanceDBStore`,
:class:`PgVectorStore`) provide full, typed signatures with documented ``TODO``
bodies. The heavy optional dependencies they will use live only in ``TODO``
comments, so importing this module never requires the ``rag`` extra.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# A dense embedding vector.
Embedding = list[float]


@dataclass(frozen=True, slots=True)
class Chunk:
    """A contiguous slice of filing text with positional metadata.

    Attributes:
        text: The chunk's text.
        index: The chunk's ordinal position within its source document.
        source: Optional identifier of the source (e.g. an accession number).
    """

    text: str
    index: int
    source: str | None = None


def chunk_text(text: str, *, max_tokens: int = 512) -> list[Chunk]:
    """Split ``text`` into ordered, non-overlapping chunks of at most ``max_tokens``.

    A pragmatic whitespace tokenizer approximates tokens by words — adequate for
    chunk sizing without pulling in a tokenizer dependency. Whitespace-only input
    yields no chunks.

    Args:
        text: The source text to chunk.
        max_tokens: Maximum number of whitespace tokens per chunk; must be > 0.

    Returns:
        The ordered chunks covering ``text``.

    Raises:
        ValueError: If ``max_tokens`` is not positive.
    """
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    words = text.split()
    return [
        Chunk(text=" ".join(words[start : start + max_tokens]), index=index)
        for index, start in enumerate(range(0, len(words), max_tokens))
    ]


@runtime_checkable
class Embedder(Protocol):
    """Turns text into dense embedding vectors."""

    def embed(self, texts: list[str]) -> list[Embedding]:
        """Return one embedding vector per input text."""
        ...


@runtime_checkable
class VectorStore(Protocol):
    """Persists chunk embeddings and answers nearest-neighbour queries."""

    def add(self, chunks: list[Chunk], embeddings: list[Embedding]) -> None:
        """Persist ``chunks`` alongside their ``embeddings`` (positionally aligned)."""
        ...

    def search(self, embedding: Embedding, k: int) -> list[Chunk]:
        """Return the ``k`` stored chunks nearest to ``embedding``."""
        ...


class SentenceTransformerEmbedder:
    """Local :class:`Embedder` backed by a ``sentence-transformers`` model."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        """Store the model name; the model itself loads lazily on first embed.

        Args:
            model_name: A ``sentence-transformers`` model identifier.
        """
        self.model_name = model_name
        self._model: object | None = None

    def embed(self, texts: list[str]) -> list[Embedding]:
        """Embed ``texts`` with the configured model.

        Args:
            texts: Input strings to embed.

        Returns:
            One embedding vector per input text.

        Raises:
            NotImplementedError: Until lazy model loading + encode is wired.
        """
        # TODO(rag): lazily `from sentence_transformers import SentenceTransformer`,
        # cache `self._model = SentenceTransformer(self.model_name)`, then return
        # `self._model.encode(texts, normalize_embeddings=True).tolist()`.
        raise NotImplementedError("SentenceTransformerEmbedder.embed: model loading pending")


class LanceDBStore:
    """Local :class:`VectorStore` backed by LanceDB (filesystem-native)."""

    def __init__(self, uri: str = "./data/lancedb", table: str = "filings") -> None:
        """Configure the store location.

        Args:
            uri: LanceDB database directory.
            table: Table name holding the filing chunks.
        """
        self.uri = uri
        self.table = table

    def add(self, chunks: list[Chunk], embeddings: list[Embedding]) -> None:
        """Persist ``chunks`` and their ``embeddings``.

        Args:
            chunks: The text chunks to store.
            embeddings: Vectors aligned positionally with ``chunks``.

        Raises:
            NotImplementedError: Until the LanceDB write path is wired.
        """
        # TODO(rag): lazily `import lancedb`, `db = lancedb.connect(self.uri)`,
        # create/open self.table, and append {text, index, source, vector} rows.
        raise NotImplementedError("LanceDBStore.add: write path pending")

    def search(self, embedding: Embedding, k: int) -> list[Chunk]:
        """Return the ``k`` nearest chunks to ``embedding``.

        Args:
            embedding: The query vector.
            k: Number of neighbours to return.

        Returns:
            The ``k`` nearest stored chunks.

        Raises:
            NotImplementedError: Until the LanceDB search path is wired.
        """
        # TODO(rag): `db.open_table(self.table).search(embedding).limit(k)` and map
        # each result row back into a Chunk.
        raise NotImplementedError("LanceDBStore.search: search path pending")


class PgVectorStore:
    """Cloud :class:`VectorStore` backed by Postgres + pgvector."""

    def __init__(self, dsn: str, table: str = "filing_chunks") -> None:
        """Configure the connection target.

        Args:
            dsn: Postgres connection string (``postgresql://...``).
            table: Table holding the filing chunks and their vectors.
        """
        self.dsn = dsn
        self.table = table

    def add(self, chunks: list[Chunk], embeddings: list[Embedding]) -> None:
        """Persist ``chunks`` and their ``embeddings``.

        Args:
            chunks: The text chunks to store.
            embeddings: Vectors aligned positionally with ``chunks``.

        Raises:
            NotImplementedError: Until the pgvector write path is wired.
        """
        # TODO(rag): lazily `import psycopg`, connect with self.dsn, and
        # `executemany` an INSERT of (text, index, source, vector) into self.table
        # (the vector column registered via pgvector's psycopg adapter).
        raise NotImplementedError("PgVectorStore.add: write path pending")

    def search(self, embedding: Embedding, k: int) -> list[Chunk]:
        """Return the ``k`` nearest chunks to ``embedding``.

        Args:
            embedding: The query vector.
            k: Number of neighbours to return.

        Returns:
            The ``k`` nearest stored chunks.

        Raises:
            NotImplementedError: Until the pgvector search path is wired.
        """
        # TODO(rag): `SELECT text, index, source FROM {table} ORDER BY vector <=> %s
        # LIMIT %s` (cosine distance) and map rows back into Chunks.
        raise NotImplementedError("PgVectorStore.search: search path pending")


def embed_and_store(chunks: list[Chunk], embedder: Embedder, store: VectorStore) -> None:
    """Embed ``chunks`` and persist them to ``store``.

    Args:
        chunks: The text chunks to index.
        embedder: The embedding backend.
        store: The vector store to write into.

    Raises:
        NotImplementedError: Until the embed → store wiring is implemented.
    """
    # TODO(rag): `embeddings = embedder.embed([c.text for c in chunks])` then
    # `store.add(chunks, embeddings)`, batching for large inputs to bound memory.
    raise NotImplementedError("embed_and_store: embed/store wiring pending")
