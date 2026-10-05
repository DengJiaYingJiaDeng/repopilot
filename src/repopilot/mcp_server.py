"""Read-only MCP server for one explicitly selected local repository."""

import argparse
from pathlib import Path
from typing import Any

from mcp.server import MCPServer

from repopilot.config import Settings
from repopilot.service import RepoPilotService


def create_mcp_server(repository: Path, settings: Settings | None = None) -> MCPServer:
    """Index a bounded repository snapshot and register four read-only tools."""
    config = settings or Settings(allowed_root=repository.resolve().parent)
    service = RepoPilotService(config)
    service.index(repository)
    server = MCPServer("RepoPilot")

    @server.tool()
    def search_code(query: str, top_k: int = 5, method: str = "bm25") -> list[dict[str, Any]]:
        """Find relevant code with path, symbol, line range, and source excerpt."""
        if not 1 <= top_k <= 10:
            raise ValueError("top_k must be between 1 and 10")
        return [
            {
                "file_path": item.chunk.file_path,
                "symbol": item.chunk.symbol_name,
                "kind": item.chunk.symbol_type,
                "start_line": item.chunk.start_line,
                "end_line": item.chunk.end_line,
                "score": item.score,
                "content": item.chunk.content[:2000],
            }
            for item in service.search(query, top_k, method)
        ]

    @server.tool()
    def read_file(path: str) -> str:
        """Read a repository-relative file captured in the indexed snapshot."""
        return service.read_file(path)[:8000]

    @server.tool()
    def find_symbol(name: str) -> list[dict[str, Any]]:
        """Find Python functions, classes, assignments, and imports in the snapshot."""
        return [
            {
                "file_path": item.chunk.file_path,
                "symbol": item.chunk.symbol_name,
                "kind": item.chunk.symbol_type,
                "start_line": item.chunk.start_line,
                "end_line": item.chunk.end_line,
                "content": item.chunk.content[:2000],
            }
            for item in service.find_symbol(name, 10)
        ]

    @server.tool()
    def find_callers(name: str) -> list[dict[str, Any]]:
        """Find candidate Python call sites by name; receiver types and aliases are unresolved."""
        return [item.model_dump() for item in service.find_callers(name)]

    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RepoPilot MCP over stdio")
    parser.add_argument("repository", type=Path, help="Repository directory to index")
    args = parser.parse_args()
    repository: Path = args.repository.resolve(strict=True)
    server = create_mcp_server(repository)
    server.run()


if __name__ == "__main__":
    main()
