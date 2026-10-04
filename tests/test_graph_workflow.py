import json
from pathlib import Path

from repopilot.agent import Investigator, ModelTurn
from repopilot.config import Settings
from repopilot.graph_workflow import build_investigation_graph
from repopilot.service import RepoPilotService


class FinalModel:
    def __init__(self, text: str) -> None:
        self.text = text

    def next_turn(
        self,
        initial_prompt: str | None,
        previous_response_id: str | None,
        tool_outputs: list[dict[str, str]],
    ) -> ModelTurn:
        return ModelTurn("1", [], self.text)


def test_graph_routes_incomplete_result_for_review(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "config.py").write_text("def load_config():\n    return 1\n")
    service = RepoPilotService(Settings(allowed_root=tmp_path))
    service.index(repo)
    graph = build_investigation_graph(Investigator(service, FinalModel("invalid")))
    state = graph.invoke({"issue_text": "config failed", "method": "bm25"})
    assert state["result"].status == "incomplete"
    assert state["review_required"] is True
    good = json.dumps(
        {
            "root_cause_hypothesis": "load_config may use the wrong value",
            "investigation_steps": ["Read config.py"],
            "test_plan": ["Check a failing configuration"],
            "evidence_files": ["config.py"],
        }
    )
    graph = build_investigation_graph(Investigator(service, FinalModel(good)))
    state = graph.invoke({"issue_text": "config failed", "method": "bm25"})
    assert state["result"].status == "complete"
    assert state["review_required"] is True
    assert state["result"].evidence_status == "insufficient"
