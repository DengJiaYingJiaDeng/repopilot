"""A small server example used by retrieval tests."""

from config import load_environment_config
from utils import validate_server_config


class MCPServer:
    def __init__(self) -> None:
        self.config = load_environment_config()

    async def start_mcp_server(self) -> None:
        validate_server_config(self.config)
