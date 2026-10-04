from pathlib import Path

from fastapi.testclient import TestClient

from repopilot.api.app import create_app
from repopilot.config import Settings

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


def test_end_to_end_api() -> None:
    client = TestClient(create_app(Settings(allowed_root=FIXTURE.parent)))
    assert client.get("/health").json() == {"status": "ok"}
    assert client.post("/search", json={"query": "config"}).status_code == 409

    indexed = client.post("/repositories/index", json={"path": str(FIXTURE)})
    assert indexed.status_code == 200
    assert indexed.json()["files_indexed"] >= 4
    assert indexed.json()["chunks_created"] >= 5

    search = client.post("/search", json={"query": "environment config", "top_k": 5})
    assert search.status_code == 200
    assert search.json()[0]["chunk"]["symbol_name"] == "load_environment_config"

    analysis = client.post("/analyze", json={"issue_text": "MCP server config", "top_k": 5})
    assert analysis.status_code == 200
    assert analysis.json()["relevant_files"]
    assert "root_cause_hypothesis" not in analysis.json()


def test_api_rejects_repository_outside_boundary(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(allowed_root=tmp_path)))
    response = client.post("/repositories/index", json={"path": str(FIXTURE)})
    assert response.status_code == 400
