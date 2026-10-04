"""An explainable lexical retrieval baseline."""

import re
from abc import ABC, abstractmethod
from collections.abc import Sequence

from repopilot.domain import CodeChunk, ScoredChunk

TOKEN = re.compile(r"[a-z0-9]+")
CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def tokens(value: str) -> set[str]:
    return set(TOKEN.findall(CAMEL_BOUNDARY.sub(" ", value).lower()))


class Retriever(ABC):
    @abstractmethod
    def index(self, chunks: Sequence[CodeChunk]) -> None:
        """Replace the searchable corpus; future methods may prepare statistics here."""

    @abstractmethod
    def search(self, query: str, top_k: int) -> list[ScoredChunk]:
        """Return the best matching chunks."""


class KeywordRetriever(Retriever):
    def __init__(self) -> None:
        self._chunks: tuple[CodeChunk, ...] = ()

    def index(self, chunks: Sequence[CodeChunk]) -> None:
        self._chunks = tuple(chunks)

    def search(self, query: str, top_k: int) -> list[ScoredChunk]:
        query_terms = tokens(query)
        if not query_terms or top_k <= 0:
            return []

        results: list[ScoredChunk] = []
        for chunk in self._chunks:
            path_hits = len(query_terms & tokens(chunk.file_path))
            name_hits = len(query_terms & tokens(chunk.symbol_name or ""))
            content_hits = len(query_terms & tokens(chunk.content))
            score = float(2 * path_hits + 4 * name_hits + content_hits)
            if score > 0:
                results.append(ScoredChunk(chunk=chunk, score=score))
        results.sort(key=lambda item: (-item.score, item.chunk.file_path, item.chunk.start_line))
        return results[:top_k]
