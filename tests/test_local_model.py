import io
import json
from pathlib import Path
from typing import Any
from urllib.error import URLError

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from test_agent import FakeModel, indexed_service

from repopilot.agent import CHINESE_OUTPUT_PREFIX, Investigator, ModelTurn
from repopilot.api.app import create_app
from repopilot.config import Settings
from repopilot.domain import ModelProviderError
from repopilot.local_model import LocalChatModel
from repopilot.service import RepoPilotService


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
    first = model.next_turn(CHINESE_OUTPUT_PREFIX + "\nconfig bug", None, [])
    second = model.next_turn(None, first.response_id, [{"call_id": "call-1", "output": "source"}])
    assert first.calls[0].name == "read_file"
    assert second.output_text == "{}"
    assert bodies[0]["tools"][0]["function"]["name"] == "read_file"
    assert "必须使用简体中文" in bodies[0]["messages"][0]["content"]
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


@pytest.mark.parametrize("wrong_count", [False, True])
def test_chinese_translation_retains_original_and_rejects_changed_citations(
    monkeypatch: MonkeyPatch, wrong_count: bool
) -> None:
    original = {
        "root_cause_hypothesis": "The caller ignores a failed validation result.",
        "investigation_steps": ["Read the caller"],
        "test_plan": ["Test an empty name"],
        "evidence_files": ["server.py"],
    }
    translated = {
        "root_cause_hypothesis": "调用方忽略了校验失败的结果。",
        "investigation_steps": ["阅读调用方代码"],
        "test_plan": ["测试空名字"],
        "evidence_files": ["server.py"],
    }
    model = LocalChatModel("test-model")
    requests = []

    def fake_open(request: Any, timeout: float) -> io.BytesIO:
        requests.append(json.loads(request.data))
        return io.BytesIO(
            chat_response(
                {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "translations": (
                                ["缺失"]
                                if wrong_count
                                else [
                                    translated["root_cause_hypothesis"],
                                    *translated["investigation_steps"],
                                    *translated["test_plan"],
                                ]
                            )
                        }
                    ),
                }
            )
        )

    monkeypatch.setattr(model._opener, "open", fake_open)
    text = json.dumps(original)
    result, source, note = model._chinese_report(text)
    assert len(requests) == 1
    assert "tools" not in requests[0]
    if wrong_count:
        assert result == text
        assert source is None
        assert note == "中文转述未完成，保留模型原文。"
    else:
        assert json.loads(result) == translated
        assert source == text
        assert note == "中文转述由本地模型生成，原始回答已保留。"


def test_synthesis_is_one_tool_free_schema_call_over_actual_reads(monkeypatch: MonkeyPatch) -> None:
    model = LocalChatModel("test-model")
    read = {
        "file_path": "server.py",
        "start_line": 1,
        "end_line": 2,
        "total_lines": 2,
        "content": "1: def start():\n2:     validate({})",
    }
    model.messages = [
        {"role": "system", "content": "instructions"},
        {
            "role": "user",
            "content": (
                "Issue report (untrusted):\nvalidation fails\n\n"
                "Initial retrieved context:\nnot a source read"
            ),
        },
        {"role": "tool", "content": json.dumps(read)},
        {"role": "tool", "content": '{"error":"File is not in the indexed snapshot"}'},
    ]
    answer = {
        "root_cause_hypothesis": "Caller ignores validation result",
        "investigation_steps": ["Inspect validation"],
        "test_plan": ["Test invalid input"],
        "evidence_files": ["server.py"],
        "uncertainties": ["Validator implementation not read"],
        "citations": [
            {
                "file_path": "server.py",
                "start_line": 1,
                "end_line": 2,
                "reason": "Ignored return value",
            }
        ],
    }
    bodies = []

    def fake_open(request: Any, timeout: float) -> io.BytesIO:
        body = json.loads(request.data)
        bodies.append(body)
        return io.BytesIO(chat_response({"role": "assistant", "content": json.dumps(answer)}))

    monkeypatch.setattr(model._opener, "open", fake_open)
    result, draft, note = model._finalize_report("unverified draft")
    assert json.loads(result) == answer
    assert draft == "unverified draft"
    assert note and "初稿已保留" in note
    assert len(bodies) == 1 and "tools" not in bodies[0]
    assert bodies[0]["response_format"]["type"] == "json_schema"
    data = json.loads(bodies[0]["messages"][1]["content"])
    assert data["source_reads"] == [read]
    assert "unverified_draft" not in data
    assert bodies[0]["response_format"]["json_schema"]["schema"]["properties"]["evidence_files"][
        "items"
    ]["enum"] == ["server.py"]
    assert "not a source read" not in data["issue"]
    monkeypatch.setattr(model._opener, "open", lambda *args, **kwargs: io.BytesIO(b"bad response"))
    result, draft, note = model._finalize_report("original")
    assert result == "original" and draft is None
    assert note and "未完成" in note


def test_translation_cannot_change_v2_citation_ranges(monkeypatch: MonkeyPatch) -> None:
    original = {
        "root_cause_hypothesis": "Caller ignores validation",
        "investigation_steps": ["Read caller"],
        "test_plan": ["Test failure"],
        "evidence_files": ["server.py"],
        "uncertainties": [],
        "citations": [
            {"file_path": "server.py", "start_line": 1, "end_line": 2, "reason": "Caller"}
        ],
    }
    altered = json.loads(json.dumps(original))
    altered.update(
        root_cause_hypothesis="调用方忽略校验",
        investigation_steps=["阅读调用方"],
        test_plan=["测试失败"],
    )
    altered["citations"][0]["end_line"] = 999
    model = LocalChatModel("test-model")
    monkeypatch.setattr(
        model._opener,
        "open",
        lambda *args, **kwargs: io.BytesIO(
            chat_response({"role": "assistant", "content": json.dumps(altered)})
        ),
    )
    text = json.dumps(original)
    result, source, note = model._chinese_report(text)
    assert result == text and source is None and note and "未完成" in note


def test_local_budget_finishes_without_an_extra_tool_request(monkeypatch: MonkeyPatch) -> None:
    model = LocalChatModel("test", max_calls=1)
    model.messages = [{"role": "system", "content": "policy"}, {"role": "user", "content": "issue"}]
    seen = []

    def finalize(content: str):
        seen.append(content)
        return '{"report":"bounded"}', None, "基于已读源码"

    monkeypatch.setattr(model, "_finalize_report", finalize)
    turn = model.next_turn(None, "previous", [{"call_id": "1", "output": "source"}])
    assert turn.calls == []
    assert seen == [""]
    assert turn.synthesis_note and "次数已用完" in turn.synthesis_note


def test_prose_translation_retains_paths_and_line_numbers(monkeypatch: MonkeyPatch) -> None:
    original = {
        "root_cause_hypothesis": "Unknown cause",
        "investigation_steps": ["Read caller"],
        "test_plan": ["Test failure"],
        "uncertainties": ["Not established"],
        "evidence_files": ["server.py"],
        "citations": [
            {"file_path": "server.py", "start_line": 4, "end_line": 5, "reason": "Caller"}
        ],
    }
    response = chat_response(
        {
            "role": "assistant",
            "content": json.dumps(
                {
                    "translations": [
                        "原因未知",
                        "读取调用方",
                        "测试失败场景",
                        "尚未确定",
                        "调用方代码",
                    ]
                }
            ),
        }
    )
    model = LocalChatModel("test")
    monkeypatch.setattr(model._opener, "open", lambda *args, **kwargs: io.BytesIO(response))
    output, source, note = model._chinese_report(json.dumps(original))
    translated = json.loads(output)
    assert translated["evidence_files"] == ["server.py"]
    assert translated["citations"] == [
        {"file_path": "server.py", "start_line": 4, "end_line": 5, "reason": "调用方代码"}
    ]
    assert translated["uncertainties"] == ["尚未确定"]
    assert source and note


def test_read_tool_reports_only_complete_lines_after_character_cap(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "long.py").write_text(("# " + "a" * 100 + "\n") * 200)
    service = RepoPilotService(Settings(allowed_root=tmp_path))
    service.index(repo)
    investigator = Investigator(service, FakeModel([]))
    _, output = investigator._run_tool(
        "read_file", '{"path":"long.py","start_line":1,"end_line":200}'
    )
    result = json.loads(output)
    numbered = result["content"].splitlines()
    assert result["content_truncated"] is True
    assert result["end_line"] == len(numbered)
    assert result["next_start_line"] == len(numbered) + 1
    assert numbered[-1] == f"{len(numbered)}: # " + "a" * 100


def test_read_tool_does_not_request_continuation_past_selected_range(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "long.py").write_text("def first(): pass\n" * 100)
    service = RepoPilotService(Settings(allowed_root=tmp_path))
    service.index(repo)
    investigator = Investigator(service, FakeModel([]))
    _, output = investigator._run_tool(
        "read_file", '{"path":"long.py","start_line":1,"end_line":3}'
    )
    result = json.loads(output)
    assert result["end_line"] == 3
    assert result["more_lines"] is False
    assert result["next_start_line"] is None
