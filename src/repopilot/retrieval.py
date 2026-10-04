"""Lexical retrieval methods over repository chunks."""

import math
import re
from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Sequence

from repopilot.domain import CodeChunk, ScoredChunk

TOKEN = re.compile(r"[a-z0-9]+")
CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def tokenize(value: str) -> list[str]:
    """Split English words, snake_case, and camelCase into lowercase terms."""
    return TOKEN.findall(CAMEL_BOUNDARY.sub(" ", value).lower())


def tokens(value: str) -> set[str]:
    return set(tokenize(value))


class Retriever(ABC):
    @abstractmethod
    def index(self, chunks: Sequence[CodeChunk]) -> None:
        """Replace the searchable corpus."""

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


class BM25Retriever(Retriever):
    """BM25 over path, symbol, and content terms, with explicit field repetition."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        if k1 <= 0 or not 0 <= b <= 1:
            raise ValueError("BM25 requires k1 > 0 and 0 <= b <= 1")
        self.k1 = k1
        self.b = b
        self._chunks: tuple[CodeChunk, ...] = ()
        self._frequencies: list[Counter[str]] = []
        self._lengths: list[int] = []
        self._document_frequency: Counter[str] = Counter()
        self._average_length = 0.0

    def index(self, chunks: Sequence[CodeChunk]) -> None:
        self._chunks = tuple(chunks)
        self._frequencies = []
        self._lengths = []
        self._document_frequency = Counter()
        for chunk in self._chunks:
            terms = (
                tokenize(chunk.file_path) * 2
                + tokenize(chunk.symbol_name or "") * 3
                + tokenize(chunk.content)
            )
            frequency = Counter(terms)
            self._frequencies.append(frequency)
            self._lengths.append(len(terms))
            self._document_frequency.update(frequency.keys())
        self._average_length = sum(self._lengths) / len(self._lengths) if self._lengths else 0.0

    def search(self, query: str, top_k: int) -> list[ScoredChunk]:
        query_terms = tokens(query)
        if not query_terms or top_k <= 0 or not self._chunks or self._average_length == 0:
            return []
        total = len(self._chunks)
        results: list[ScoredChunk] = []
        for chunk, frequency, length in zip(
            self._chunks, self._frequencies, self._lengths, strict=True
        ):
            score = 0.0
            for term in query_terms:
                count = frequency[term]
                if count == 0:
                    continue
                df = self._document_frequency[term]
                idf = math.log1p((total - df + 0.5) / (df + 0.5))
                norm = self.k1 * (1 - self.b + self.b * length / self._average_length)
                score += idf * count * (self.k1 + 1) / (count + norm)
            if score > 0:
                results.append(ScoredChunk(chunk=chunk, score=score))
        results.sort(key=lambda item: (-item.score, item.chunk.file_path, item.chunk.start_line))
        return results[:top_k]
