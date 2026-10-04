from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from repopilot.api.app import create_app
from repopilot.config import Settings
from repopilot.domain import CodeChunk
from repopilot.retrieval import HybridRetriever, KeywordRetriever, VectorRetriever
from repopilot.service import RepoPilotService


class FakeEmbedder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [[1.0, 0.0] if "alpha" in text else [0.0, 1.0] for text in texts]


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


def test_vector_search_and_reindex() -> None:
    fake = FakeEmbedder()
    retriever = VectorRetriever(fake)
    retriever.index([chunk("beta"), chunk("alpha")])
    assert retriever.search("alpha", 1)[0].chunk.id == "alpha"
    retriever.index([chunk("beta")])
    assert [item.chunk.id for item in retriever.search("alpha", 10)] == ["beta"]


def test_hybrid_fuses_unique_chunks() -> None:
    hybrid = HybridRetriever(KeywordRetriever(), VectorRetriever(FakeEmbedder()))
    hybrid.index([chunk("alpha"), chunk("beta")])
    results = hybrid.search("alpha", 2)
    assert results[0].chunk.id == "alpha"
    assert len({item.chunk.id for item in results}) == len(results)


def test_service_indexes_embeddings_once(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "alpha.py").write_text("def alpha():\n    return 1\n")
    fake = FakeEmbedder()
    service = RepoPilotService(Settings(allowed_root=tmp_path), embedder=fake)
    service.index(repo)
    assert len(fake.calls) == 1
    assert service.search("alpha", 1, "vector")
    assert service.search("alpha", 1, "hybrid")
    assert len(fake.calls) == 3


def test_api_reports_unconfigured_vector(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "alpha.py").write_text("def alpha():\n    return 1\n")
    client = TestClient(create_app(Settings(allowed_root=tmp_path)))
    assert client.post("/repositories/index", json={"path": str(repo)}).status_code == 200
    response = client.post("/search", json={"query": "alpha", "method": "vector"})
    assert response.status_code == 400
    assert "Unknown retrieval method" in response.json()["detail"]


def test_vector_rejects_malformed_vectors() -> None:
    class BadEmbedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[1.0]] if len(texts) == 1 else [[1.0], [1.0, 2.0]]

    with pytest.raises(ValueError, match="consistent"):
        VectorRetriever(BadEmbedder()).index([chunk("alpha"), chunk("beta")])


def test_failed_reindex_disables_stale_search(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "alpha.py").write_text("def alpha():\n    return 1\n")
    (second / "beta.py").write_text("def beta():\n    return 2\n")

    class FailingEmbedder(FakeEmbedder):
        def embed(self, texts: list[str]) -> list[list[float]]:
            if any("beta" in text for text in texts):
                raise RuntimeError("embedding service failed")
            return super().embed(texts)

    from repopilot.domain import IndexNotReadyError

    service = RepoPilotService(Settings(allowed_root=tmp_path), embedder=FailingEmbedder())
    service.index(first)
    with pytest.raises(RuntimeError, match="embedding service failed"):
        service.index(second)
    with pytest.raises(IndexNotReadyError):
        service.search("alpha", 1)
