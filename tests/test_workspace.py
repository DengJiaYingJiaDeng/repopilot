from pathlib import Path

from fastapi.testclient import TestClient
from test_agent import indexed_service

from repopilot.agent import Investigator, ModelTurn
from repopilot.api.app import create_app
from repopilot.config import Settings


def test_workspace_reports_config_without_exposing_a_key(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(allowed_root=tmp_path)))
    workspace = client.get("/workspace").json()
    assert workspace["allowed_root"] == str(tmp_path)
    assert workspace["example_repository"] is None
    assert workspace["methods"] == ["keyword", "bm25"]
    assert workspace["investigation_configured"] is False
    assert "api_key" not in str(workspace)


def test_frontend_origin_allowed_but_arbitrary_origin_rejected(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(allowed_root=tmp_path)))

    def preflight(origin: str):
        return client.options(
            "/investigate",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )

    assert (
        preflight("http://127.0.0.1:5173").headers["access-control-allow-origin"]
        == "http://127.0.0.1:5173"
    )
    assert preflight("https://unrelated.example").status_code == 400


def test_chinese_output_requirement_is_added_outside_issue_text(tmp_path: Path) -> None:
    class CapturingModel:
        prompt = ""

        def next_turn(self, initial_prompt, previous_response_id, tool_outputs):
            self.prompt = initial_prompt
            return ModelTurn("1", [], "invalid")

    model = CapturingModel()
    Investigator(indexed_service(tmp_path), model).investigate("config bug", response_language="zh")
    assert model.prompt.startswith("Output requirement:")
    assert "Simplified Chinese" in model.prompt
    assert "config bug" in model.prompt
