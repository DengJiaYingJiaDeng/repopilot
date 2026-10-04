from pathlib import Path

from test_agent import FakeModel

from repopilot.agent import Investigator
from repopilot.callgraph import index_calls
from repopilot.config import Settings
from repopilot.service import RepoPilotService


def test_call_candidates_ignore_comments_and_strings_and_keep_scope() -> None:
    source = """# validate(config)
text = "validate(config)"
def validate(x): return bool(x)
class Server:
    async def start(self):
        validate(self.config)
        other.validate(self.config)
"""
    sites = index_calls({"server.py": source, "README.md": "validate(config)"})["validate"]
    assert len(sites) == 2
    assert [s.call_line for s in sites] == [6, 7]
    assert all(s.caller == "Server.start" and s.match_kind == "name_candidate" for s in sites)
    assert sites[1].callee == "other.validate"
    assert "unresolved" in sites[1].limitation


def test_caller_tool_uses_snapshot_and_prioritizes_source_over_tests(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "server.py").write_text("def start():\n    validate({})\n")
    (repo / "test_server.py").write_text("def test_start():\n    validate({})\n")
    service = RepoPilotService(Settings(allowed_root=tmp_path))
    service.index(repo)
    (repo / "server.py").write_text("def start(): pass\n")
    assert [s.file_path for s in service.find_callers("utils.validate")] == [
        "server.py",
        "test_server.py",
    ]
    agent = Investigator(service, FakeModel([]))
    _, output = agent._run_tool("find_callers", '{"name":"validate"}')
    assert "name_candidate" in output
    assert "server.py" in output
    service.index(repo)
    assert [s.file_path for s in service.find_callers("validate")] == ["test_server.py"]
    assert service.find_callers("missing") == []
