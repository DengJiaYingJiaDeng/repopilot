import json
from pathlib import Path

from fastapi.testclient import TestClient

from repopilot.agent import Investigator, ModelTurn, ToolCall
from repopilot.api.app import create_app
from repopilot.config import Settings
from repopilot.service import RepoPilotService


class FakeModel:
    def __init__(self, turns: list[ModelTurn]) -> None:
        self.turns = iter(turns)
        self.received: list[list[dict[str, str]]] = []

    def next_turn(
        self,
        initial_prompt: str | None,
        previous_response_id: str | None,
        tool_outputs: list[dict[str, str]],
    ) -> ModelTurn:
        self.received.append(tool_outputs)
        return next(self.turns)


def indexed_service(tmp_path: Path) -> RepoPilotService:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "config.py").write_text("def load_config():\n    return 'setting'\n")
    service = RepoPilotService(Settings(allowed_root=tmp_path))
    service.index(repo)
    return service


def test_agent_uses_tools_and_returns_grounded_hypothesis(tmp_path: Path) -> None:
    service = indexed_service(tmp_path)
    model = FakeModel(
        [
            ModelTurn(
                "1", [ToolCall(call_id="a", name="find_symbol", arguments='{"name":"load"}')], ""
            ),
            ModelTurn(
                "2", [ToolCall(call_id="b", name="read_file", arguments='{"path":"config.py"}')], ""
            ),
            ModelTurn(
                "3",
                [],
                json.dumps(
                    {
                        "root_cause_hypothesis": "Configuration loading may use a stale value.",
                        "investigation_steps": ["Inspect load_config"],
                        "test_plan": ["Add a regression test for the failing setting"],
                        "evidence_files": ["config.py"],
                    }
                ),
            ),
        ]
    )
    result = Investigator(service, model).investigate("config setting failure")
    assert result.status == "complete"
    assert len(result.tool_trace) == 2
    assert "load_config" in model.received[1][0]["output"]
    assert "def load_config" in model.received[2][0]["output"]
    assert result.evidence_files == ["config.py"]


def test_agent_cannot_read_outside_snapshot(tmp_path: Path) -> None:
    service = indexed_service(tmp_path)
    model = FakeModel(
        [
            ModelTurn(
                "1", [ToolCall(call_id="a", name="read_file", arguments='{"path":"../secret"}')], ""
            ),
            ModelTurn("2", [], "not json"),
        ]
    )
    result = Investigator(service, model).investigate("config")
    assert result.status == "incomplete"
    assert "not in the indexed snapshot" in model.received[1][0]["output"]


def test_agent_stops_after_tool_limit(tmp_path: Path) -> None:
    service = indexed_service(tmp_path)
    call = ToolCall(call_id="a", name="search_code", arguments='{"query":"config"}')
    model = FakeModel([ModelTurn("1", [call, call], "")])
    result = Investigator(service, model, max_calls=1).investigate("config")
    assert result.status == "incomplete"
    assert result.limitation == "Tool call limit reached"
    assert len(result.tool_trace) == 1


def test_investigate_api_requires_model(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(allowed_root=tmp_path)))
    response = client.post("/investigate", json={"issue_text": "config bug"})
    assert response.status_code == 503


def test_agent_rejects_unseen_evidence_file(tmp_path: Path) -> None:
    service = indexed_service(tmp_path)
    repo = tmp_path / "repo"
    (repo / "other.py").write_text("def unrelated():\n    return 2\n")
    service.index(repo)
    answer = json.dumps(
        {
            "root_cause_hypothesis": "Speculation",
            "investigation_steps": ["Inspect"],
            "test_plan": ["Test"],
            "evidence_files": ["other.py"],
        }
    )
    result = Investigator(service, FakeModel([ModelTurn("1", [], answer)])).investigate("config")
    assert result.status == "incomplete"
    assert result.limitation == "Model cited a file absent from observed evidence"
