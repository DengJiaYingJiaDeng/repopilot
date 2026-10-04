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
    bm25 = client.post(
        "/search", json={"query": "environment config", "top_k": 5, "method": "bm25"}
    )
    assert bm25.status_code == 200
    assert any(item["chunk"]["symbol_name"] == "load_environment_config" for item in bm25.json())

    analysis = client.post("/analyze", json={"issue_text": "MCP server config", "top_k": 5})
    assert analysis.status_code == 200
    assert analysis.json()["relevant_files"]
    assert "root_cause_hypothesis" not in analysis.json()


def test_api_rejects_repository_outside_boundary(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(allowed_root=tmp_path)))
    response = client.post("/repositories/index", json={"path": str(FIXTURE)})
    assert response.status_code == 400


def test_investigate_api_with_fake_model() -> None:
    import json

    from pydantic import SecretStr

    from repopilot.agent import ModelTurn

    class FinalModel:
        def next_turn(
            self,
            initial_prompt: str | None,
            previous_response_id: str | None,
            tool_outputs: list[dict[str, str]],
        ) -> ModelTurn:
            answer = {
                "root_cause_hypothesis": "The environment setting may not load.",
                "investigation_steps": ["Inspect config.py"],
                "test_plan": ["Test missing environment variable"],
                "evidence_files": ["config.py"],
            }
            return ModelTurn("1", [], json.dumps(answer))

    app = create_app(
        Settings(
            allowed_root=FIXTURE.parent,
            investigation_model="test-model",
            openai_api_key=SecretStr("test-key"),
            investigation_workflow="langgraph",
        )
    )
    app.state.investigator.model = FinalModel()
    client = TestClient(app)
    assert client.post("/repositories/index", json={"path": str(FIXTURE)}).status_code == 200
    response = client.post("/investigate", json={"issue_text": "environment config failure"})
    assert response.status_code == 200
    assert response.json()["status"] == "complete"
    assert response.json()["evidence_files"] == ["config.py"]
