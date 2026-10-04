"""Configuration for a tiny MCP service."""

import os


def load_environment_config() -> dict[str, str]:
    return {"server_name": os.getenv("MCP_SERVER_NAME", "demo")}
