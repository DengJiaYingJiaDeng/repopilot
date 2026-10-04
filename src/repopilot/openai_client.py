"""Create the optional OpenAI SDK client with proxy configuration."""

import os
from importlib import import_module
from typing import Any


def create_openai_client(api_key: str) -> Any:
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required")
    openai = import_module("openai")
    proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
    if proxy is None:
        proxy = os.getenv("ALL_PROXY") or os.getenv("all_proxy")
    if proxy and proxy.startswith("socks://"):
        proxy = "socks5://" + proxy.removeprefix("socks://")
    if proxy:
        httpx = import_module("httpx")
        return openai.OpenAI(api_key=api_key, http_client=httpx.Client(proxy=proxy))
    return openai.OpenAI(api_key=api_key)
