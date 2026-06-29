"""Retrieval + answer synthesis interface for RAG over filings (stub).

:class:`Retriever` ties an :class:`~tessera.rag.chunk_embed.Embedder` and
:class:`~tessera.rag.chunk_embed.VectorStore` to Anthropic-API answer synthesis.
The bodies are documented ``TODO``\\ s; :meth:`Retriever.answer` performs the one
piece of real logic — failing fast when no Anthropic key is configured. The
Anthropic SDK is referenced only in a ``TODO`` comment so the core installs
without the ``rag`` extra.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tessera.config import get_settings
from tessera.errors import ConfigError

if TYPE_CHECKING:
    from tessera.config import Settings
    from tessera.rag.chunk_embed import Chunk, Embedder, VectorStore

# Synthesis uses the latest Claude model; never hardcode an older id here.
DEFAULT_ANSWER_MODEL = "claude-opus-4-8"


class Retriever:
    """Vector-search retrieval with Anthropic answer synthesis over filings."""

    def __init__(
        self,
        embedder: Embedder,
        store: VectorStore,
        *,
        settings: Settings | None = None,
        model: str = DEFAULT_ANSWER_MODEL,
    ) -> None:
        """Wire the retriever to its embedding/store backends and synthesis model.

        Args:
            embedder: Backend that embeds the query for vector search.
            store: Vector store searched for relevant chunks.
            settings: Application settings; defaults to the process-wide instance.
            model: Anthropic model id used for answer synthesis.
        """
        self._embedder = embedder
        self._store = store
        self._settings = settings or get_settings()
        self._model = model

    def search(self, query: str, k: int = 5) -> list[Chunk]:
        """Return the ``k`` filing chunks most relevant to ``query``.

        Args:
            query: The natural-language query.
            k: Number of chunks to retrieve.

        Returns:
            The ``k`` most relevant chunks, nearest first.

        Raises:
            NotImplementedError: Until embed → vector-search is implemented.
        """
        # TODO(rag): `vector = self._embedder.embed([query])[0]` then
        # `return self._store.search(vector, k)`.
        raise NotImplementedError("Retriever.search: embed/search wiring pending")

    def answer(self, query: str) -> str:
        """Answer ``query`` by retrieving filing context and synthesizing with Claude.

        Args:
            query: The natural-language question.

        Returns:
            The synthesized, source-grounded answer.

        Raises:
            ConfigError: If no Anthropic API key is configured.
            NotImplementedError: Until prompt construction + synthesis is implemented.
        """
        if self._settings.anthropic_api_key is None:
            raise ConfigError(
                "anthropic_api_key is not set; it is required for RAG answer synthesis"
            )
        # TODO(rag): `chunks = self.search(query)`; build a grounded prompt that
        # cites each chunk's source; lazily `from anthropic import Anthropic`; call
        # `Anthropic(api_key=...).messages.create(model=self._model, ...)`; return
        # the concatenated text content.
        raise NotImplementedError("Retriever.answer: prompt + synthesis pending")
