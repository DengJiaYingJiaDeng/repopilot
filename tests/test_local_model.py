import io
import json
from pathlib import Path
from typing import Any
from urllib.error import URLError

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from test_agent import FakeModel, indexed_service

from repopilot.agent import Investigator, ModelTurn
from repopilot.api.app import create_app
from repopilot.config import Settings
from repopilot.domain import ModelProviderError
from repopilot.local_model import LocalChatModel


def chat_response(message: dict[str, Any], finish_reason: str = "stop") -> bytes:
    return json.dumps({"choices": [{"message": message, "finish_reason": finish_reason}]}).encode()


def test_local_model_preserves_tool_protocol(monkeypatch: MonkeyPatch) -> None:
    model = LocalChatModel("test-model")
    bodies = []
    replies = iter(
        [
            chat_response(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "read_file", "arguments": '{"path":"config.py"}'},
                        }
                    ],
                },
                "tool_calls",
            ),
            chat_response({"role": "assistant", "content": "{}", "tool_calls": None}),
        ]
    )

    def fake_open(request: Any, timeout: float) -> io.BytesIO:
        assert request.full_url == "http://127.0.0.1:8081/v1/chat/completions"
        assert timeout == 120
        bodies.append(json.loads(request.data))
        return io.BytesIO(next(replies))

    monkeypatch.setattr(model._opener, "open", fake_open)
    first = model.next_turn("config bug", None, [])
    second = model.next_turn(None, first.response_id, [{"call_id": "call-1", "output": "source"}])
    assert first.calls[0].name == "read_file"
    assert second.output_text == "{}"
    assert bodies[0]["tools"][0]["function"]["name"] == "read_file"
    messages = bodies[1]["messages"]
    assert [item["role"] for item in messages] == ["system", "user", "assistant", "tool"]
    assert messages[-1] == {"role": "tool", "tool_call_id": "call-1", "content": "source"}


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/v1",
        "http://192.168.1.2/v1",
        "http://localhost@evil.com/v1",
        "http://user:password@127.0.0.1/v1",
        "http://127.0.0.1/v1?key=secret",
    ],
)
def test_local_model_refuses_nonlocal_or_credential_urls(url: str) -> None:
    with pytest.raises(ValueError, match="loopback"):
        LocalChatModel("test", url)


@pytest.mark.parametrize(
    "reply",
    [
        b"not json",
        b'{"choices": []}',
        chat_response({"role": "assistant", "content": "partial"}, "length"),
        chat_response({"role": "assistant", "content": {"invalid": True}}),
    ],
)
def test_local_model_rejects_invalid_responses(reply: bytes, monkeypatch: MonkeyPatch) -> None:
    model = LocalChatModel("test")
    monkeypatch.setattr(model._opener, "open", lambda *args, **kwargs: io.BytesIO(reply))
    with pytest.raises(ModelProviderError):
        model.next_turn("bug", None, [])


def test_local_api_without_key_reports_provider_failure(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    def unavailable(*args: Any, **kwargs: Any) -> Any:
        raise URLError("private transport detail must not reach the user")

    monkeypatch.setattr("urllib.request.OpenerDirector.open", unavailable)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "config.py").write_text("def config(): return 1\n")
    client = TestClient(
        create_app(
            Settings(
                allowed_root=tmp_path,
                investigation_provider="local",
                investigation_model="qwen3-4b",
            )
        )
    )
    assert client.post("/repositories/index", json={"path": str(repo)}).status_code == 200
    result = client.post("/investigate", json={"issue_text": "config bug"})
    assert result.status_code == 200
    assert result.json()["status"] == "incomplete"
    assert result.json()["review_required"] is True
    assert result.json()["limitation"] == "Local model server is unavailable or timed out"


def test_each_investigation_gets_a_fresh_model(tmp_path: Path) -> None:
    service = indexed_service(tmp_path)
    models = []

    def factory() -> FakeModel:
        model = FakeModel([ModelTurn("1", [], "invalid json")])
        models.append(model)
        return model

    investigator = Investigator(service, model_factory=factory)
    assert investigator.investigate("first config issue").status == "incomplete"
    assert investigator.investigate("second config issue").status == "incomplete"
    assert len(models) == 2
    assert models[0] is not models[1]
    assert models[0].received == models[1].received == [[]]


def test_read_tool_reaches_code_beyond_first_excerpt(tmp_path: Path) -> None:
    service = indexed_service(tmp_path)
    path = tmp_path / "repo" / "long.py"
    path.write_text("# padding for a long source file\n" * 300 + "def target(): return 42\n")
    service.index(path.parent)
    investigator = Investigator(service, FakeModel([]))
    _, output = investigator._run_tool(
        "read_file",
        json.dumps(
            {
                "path": "long.py",
                "start_line": 300,
                "end_line": 301,
            }
        ),
    )
    parsed = json.loads(output)
    assert "301: def target(): return 42" in parsed["content"]
    assert parsed["end_line"] == parsed["total_lines"] == 301
    assert parsed["more_lines"] is False
    _, bad = investigator._run_tool("read_file", '{"path":"long.py","start_line":999}')
    assert "error" in json.loads(bad)
