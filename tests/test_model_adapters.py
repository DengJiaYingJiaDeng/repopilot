from types import SimpleNamespace
from typing import Any

from pytest import MonkeyPatch

from repopilot.agent import OpenAIInvestigationModel
from repopilot.embeddings import OpenAIEmbedder


class FakeEmbeddings:
    def create(self, model: str, input: list[str]) -> Any:
        assert model == "test-model"
        assert input == ["alpha", "beta"]
        return SimpleNamespace(
            data=[
                SimpleNamespace(index=1, embedding=[0.0, 1.0]),
                SimpleNamespace(index=0, embedding=[1.0, 0.0]),
            ]
        )


def test_openai_embeddings_preserve_input_order(monkeypatch: MonkeyPatch) -> None:
    fake = SimpleNamespace(embeddings=FakeEmbeddings())
    monkeypatch.setattr("repopilot.embeddings.create_openai_client", lambda key: fake)
    provider = OpenAIEmbedder("test-key", "test-model")
    assert provider.embed(["alpha", "beta"]) == [[1.0, 0.0], [0.0, 1.0]]


class FakeResponses:
    def __init__(self) -> None:
        self.kwargs: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.kwargs.append(kwargs)
        if len(self.kwargs) == 1:
            return SimpleNamespace(
                id="response-1",
                output=[
                    SimpleNamespace(
                        type="function_call",
                        call_id="call-1",
                        name="search_code",
                        arguments='{"query":"bug","top_k":1,"method":"bm25"}',
                    )
                ],
                output_text="",
            )
        return SimpleNamespace(id="response-2", output=[], output_text="{}")


def test_openai_model_passes_tool_outputs_to_previous_response(monkeypatch: MonkeyPatch) -> None:
    responses = FakeResponses()
    fake = SimpleNamespace(responses=responses)
    monkeypatch.setattr("repopilot.agent.create_openai_client", lambda key: fake)
    model = OpenAIInvestigationModel("test-key", "test-model")
    first = model.next_turn("issue", None, [])
    assert first.calls[0].name == "search_code"
    model.next_turn(
        None,
        first.response_id,
        [{"type": "function_call_output", "call_id": "call-1", "output": "[]"}],
    )
    assert responses.kwargs[1]["previous_response_id"] == "response-1"
    assert responses.kwargs[1]["input"][0]["call_id"] == "call-1"
