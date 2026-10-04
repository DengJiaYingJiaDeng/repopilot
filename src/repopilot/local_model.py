"""A per-investigation session for a local llama.cpp compatible chat server."""

import json
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from repopilot.agent import INSTRUCTIONS, TOOL_SCHEMAS, ModelTurn, ToolCall
from repopilot.domain import ModelProviderError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        raise ModelProviderError("Local model redirects are not allowed")


class LocalChatModel:
    """Keep chat history within one run and send requests only to a loopback server."""

    def __init__(
        self, model: str, base_url: str = "http://127.0.0.1:8081/v1", timeout: float = 120
    ) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Local model URL must be an HTTP loopback address without credentials")
        self.model = model
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.timeout = timeout
        self.messages: list[dict[str, Any]] = []
        self._opener = build_opener(ProxyHandler({}), NoRedirect())

    def next_turn(
        self,
        initial_prompt: str | None,
        previous_response_id: str | None,
        tool_outputs: list[dict[str, str]],
    ) -> ModelTurn:
        if previous_response_id is None:
            if initial_prompt is None:
                raise ValueError("The first local model turn requires an issue prompt")
            self.messages = [
                {
                    "role": "system",
                    "content": INSTRUCTIONS
                    + (
                        "\nYour first response MUST call read_file on a relevant implementation "
                        "path and line range from the supplied context. Do not output the "
                        "final JSON report on the first turn."
                    ),
                },
                {"role": "user", "content": initial_prompt},
            ]
        else:
            self.messages.extend(
                {"role": "tool", "tool_call_id": item["call_id"], "content": item["output"]}
                for item in tool_outputs
            )
        tools: list[dict[str, Any]] = [
            {
                "type": "function",
                "function": {
                    "name": item["name"],
                    "description": item["description"],
                    "parameters": item["parameters"],
                },
            }
            for item in TOOL_SCHEMAS
        ]
        # This server version accepts string tool_choice values. Offer only read_file
        # on the first turn so a final answer must follow an actual source read.
        if previous_response_id is None:
            tools = [tool for tool in tools if tool["function"]["name"] == "read_file"]
        body = {
            "model": self.model,
            "messages": self.messages,
            "tools": tools,
            "parallel_tool_calls": False,
            "tool_choice": "required" if previous_response_id is None else "auto",
            "temperature": 0,
            "max_tokens": 1536,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        request = Request(
            self.url,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                data = response.read(2_000_001)
            if len(data) > 2_000_000:
                raise ModelProviderError("Local model response exceeded the size limit")
            payload = json.loads(data)
            choice = payload["choices"][0]
            if choice.get("finish_reason") == "length":
                raise ModelProviderError("Local model reached its output token limit")
            message = choice["message"]
            if not isinstance(message, dict) or message.get("role") != "assistant":
                raise ModelProviderError("Local model returned an invalid assistant message")
            calls = [
                ToolCall(
                    call_id=item["id"],
                    name=item["function"]["name"],
                    arguments=item["function"]["arguments"],
                )
                for item in (message.get("tool_calls") or [])
            ]
            if previous_response_id is None and not calls:
                raise ModelProviderError("Local model did not perform the required source read")
            content = message.get("content") or ""
            if not isinstance(content, str):
                raise ModelProviderError("Local model returned non-text content")
        except HTTPError as exc:
            raise ModelProviderError(f"Local model server returned HTTP {exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ModelProviderError("Local model server is unavailable or timed out") from exc
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ModelProviderError("Local model server returned malformed chat output") from exc
        self.messages.append(message)
        return ModelTurn(str(uuid.uuid4()), calls, content)
