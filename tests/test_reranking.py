from collections.abc import Sequence

import pytest

from repopilot.domain import CodeChunk
from repopilot.reranking import RerankedRetriever
from repopilot.retrieval import KeywordRetriever


def chunk(name: str) -> CodeChunk:
    return CodeChunk(
        id=name,
        repository="repo",
        file_path=f"{name}.py",
        language="python",
        symbol_type="function",
        symbol_name=name,
        content=f"def {name}(): pass",
        start_line=1,
        end_line=1,
    )


class ReverseReranker:
    def score(self, query: str, chunks: Sequence[CodeChunk]) -> list[float]:
        return [float(index) for index, _ in enumerate(chunks)]


def test_reranker_changes_candidate_order() -> None:
    retriever = RerankedRetriever(KeywordRetriever(), ReverseReranker(), candidates=2)
    retriever.index([chunk("alpha_one"), chunk("alpha_two")])
    baseline = retriever.first_stage.search("alpha", 2)
    reranked = retriever.search("alpha", 2)
    assert [item.chunk.id for item in reranked] == [baseline[1].chunk.id, baseline[0].chunk.id]


def test_reranker_rejects_wrong_count() -> None:
    class BrokenReranker:
        def score(self, query: str, chunks: Sequence[CodeChunk]) -> list[float]:
            return []

    retriever = RerankedRetriever(KeywordRetriever(), BrokenReranker())
    retriever.index([chunk("alpha")])
    with pytest.raises(ValueError, match="wrong number"):
        retriever.search("alpha", 1)
