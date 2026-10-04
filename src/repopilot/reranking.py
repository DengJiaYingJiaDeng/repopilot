"""Optional cross-encoder reranking of retrieved code chunks."""

from collections.abc import Sequence
from importlib import import_module
from typing import Protocol

from repopilot.domain import CodeChunk, ScoredChunk
from repopilot.retrieval import Retriever


class Reranker(Protocol):
    def score(self, query: str, chunks: Sequence[CodeChunk]) -> list[float]:
        """Return one relevance score per candidate, in candidate order."""


class CrossEncoderReranker:
    def __init__(self, model: str = "cross-encoder/ms-marco-MiniLM-L6-v2") -> None:
        sentence_transformers = import_module("sentence_transformers")
        self._model = sentence_transformers.CrossEncoder(model)

    def score(self, query: str, chunks: Sequence[CodeChunk]) -> list[float]:
        if not chunks:
            return []
        pairs = [
            (query, f"{chunk.file_path} {chunk.symbol_name or ''}\n{chunk.content[:4000]}")
            for chunk in chunks
        ]
        return [float(value) for value in self._model.predict(pairs)]


class RerankedRetriever(Retriever):
    """Rerank a bounded set from an existing first-stage retriever."""

    def __init__(self, first_stage: Retriever, reranker: Reranker, candidates: int = 20) -> None:
        if candidates <= 0:
            raise ValueError("candidates must be positive")
        self.first_stage, self.reranker, self.candidates = first_stage, reranker, candidates

    def index(self, chunks: Sequence[CodeChunk]) -> None:
        self.first_stage.index(chunks)

    def search(self, query: str, top_k: int) -> list[ScoredChunk]:
        if not query.strip() or top_k <= 0:
            return []
        candidates = self.first_stage.search(query, self.candidates)
        if not candidates:
            return []
        scores = self.reranker.score(query, [item.chunk for item in candidates])
        if len(scores) != len(candidates):
            raise ValueError("Reranker returned the wrong number of scores")
        results = [
            ScoredChunk(chunk=item.chunk, score=score)
            for item, score in zip(candidates, scores, strict=True)
        ]
        results.sort(key=lambda item: (-item.score, item.chunk.file_path, item.chunk.start_line))
        return results[:top_k]
