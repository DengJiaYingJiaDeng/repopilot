from pathlib import Path

import pytest
from mcp import Client

from repopilot.mcp_server import create_mcp_server

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_mcp_search_read_and_symbol_tools() -> None:
    server = create_mcp_server(FIXTURE.resolve())
    async with Client(server) as client:
        search = await client.call_tool("search_code", {"query": "environment config", "top_k": 3})
        assert search.structured_content is not None
        assert search.structured_content["result"][0]["symbol"] == "load_environment_config"
        read = await client.call_tool("read_file", {"path": "config.py"})
        assert read.structured_content is not None
        assert "load_environment_config" in read.structured_content["result"]
        symbols = await client.call_tool("find_symbol", {"name": "start_mcp"})
        assert symbols.structured_content is not None
        assert symbols.structured_content["result"][0]["symbol"].endswith("start_mcp_server")

        callers = await client.call_tool("find_callers", {"name": "validate_server_config"})
        assert callers.structured_content is not None
        assert callers.structured_content["result"][0]["file_path"] == "mcp_server.py"
        assert callers.structured_content["result"][0]["match_kind"] == "name_candidate"
