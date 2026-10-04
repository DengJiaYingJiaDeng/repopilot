from repopilot.domain import CodeChunk
from repopilot.retrieval import BM25Retriever


def chunk(identifier: str, content: str) -> CodeChunk:
    return CodeChunk(
        id=identifier,
        repository="sample",
        file_path=f"{identifier}.py",
        language="python",
        symbol_type="module",
        content=content,
        start_line=1,
        end_line=1,
    )


def test_bm25_normalizes_document_length() -> None:
    retriever = BM25Retriever()
    retriever.index([chunk("short", "target"), chunk("long", "target " + "filler " * 100)])
    matches = retriever.search("target", 2)
    assert [item.chunk.id for item in matches] == ["short", "long"]
    assert matches[0].score > matches[1].score


def test_bm25_reindex_resets_statistics_and_empty_queries() -> None:
    retriever = BM25Retriever()
    retriever.index([chunk("first", "rarealpha")])
    assert retriever.search("rarealpha", 1)
    retriever.index([chunk("second", "rarebeta")])
    assert retriever.search("rarealpha", 1) == []
    assert retriever.search("  ", 1) == []
    assert retriever.search("rarebeta", 1)[0].chunk.id == "second"


def test_bm25_rejects_invalid_parameters() -> None:
    for k1, b in ((0, 0.75), (1.5, -0.1), (1.5, 1.1)):
        try:
            BM25Retriever(k1=k1, b=b)
        except ValueError:
            continue
        raise AssertionError("invalid BM25 parameters were accepted")
