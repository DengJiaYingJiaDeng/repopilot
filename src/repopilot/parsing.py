"""Convert Python and Markdown files into searchable chunks."""

import ast
import hashlib
import re

from repopilot.domain import CodeChunk, SymbolType
from repopilot.ingestion import SourceFile

HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$")


def _chunk_id(file_path: str, symbol_type: SymbolType, start_line: int, name: str) -> str:
    key = f"{file_path}:{symbol_type}:{start_line}:{name}"
    return hashlib.sha256(key.encode()).hexdigest()[:20]


def parse_python(file: SourceFile, repository: str) -> list[CodeChunk]:
    """Extract a module and its named classes/functions using Python's AST."""
    tree = ast.parse(file.content, filename=file.relative_path)
    lines = file.content.splitlines(keepends=True)
    chunks: list[CodeChunk] = [
        CodeChunk(
            id=_chunk_id(file.relative_path, "module", 1, file.relative_path),
            repository=repository,
            file_path=file.relative_path,
            language="python",
            symbol_name=file.relative_path,
            symbol_type="module",
            content=file.content,
            start_line=1,
            end_line=max(1, len(lines)),
        )
    ]

    def visit(node: ast.AST, parents: tuple[str, ...]) -> None:
        symbol_type: SymbolType | None = None
        if isinstance(node, ast.ClassDef):
            symbol_type = "class"
        elif isinstance(node, ast.AsyncFunctionDef):
            symbol_type = "async_function"
        elif isinstance(node, ast.FunctionDef):
            symbol_type = "function"

        next_parents = parents
        if symbol_type is not None:
            assert isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            qualified_name = ".".join((*parents, node.name))
            end_line = node.end_lineno or node.lineno
            chunks.append(
                CodeChunk(
                    id=_chunk_id(file.relative_path, symbol_type, node.lineno, qualified_name),
                    repository=repository,
                    file_path=file.relative_path,
                    language="python",
                    symbol_name=qualified_name,
                    symbol_type=symbol_type,
                    content="".join(lines[node.lineno - 1 : end_line]),
                    start_line=node.lineno,
                    end_line=end_line,
                    parent_symbol=".".join(parents) or None,
                )
            )
            next_parents = (*parents, node.name)

        for child in ast.iter_child_nodes(node):
            visit(child, next_parents)

    visit(tree, ())
    return chunks


def parse_markdown(file: SourceFile, repository: str) -> list[CodeChunk]:
    """Split Markdown at headings, keeping line ranges for citations."""
    lines = file.content.splitlines(keepends=True)
    if not lines:
        return []
    boundaries: list[tuple[int, str]] = []
    for number, line in enumerate(lines, 1):
        match = HEADING.match(line)
        if match:
            boundaries.append((number, match.group(1)))
    if not boundaries or boundaries[0][0] != 1:
        boundaries.insert(0, (1, file.relative_path))

    chunks: list[CodeChunk] = []
    for position, (start, heading) in enumerate(boundaries):
        end = boundaries[position + 1][0] - 1 if position + 1 < len(boundaries) else len(lines)
        content = "".join(lines[start - 1 : end])
        if not content.strip():
            continue
        chunks.append(
            CodeChunk(
                id=_chunk_id(file.relative_path, "markdown_section", start, heading),
                repository=repository,
                file_path=file.relative_path,
                language="markdown",
                symbol_name=heading,
                symbol_type="markdown_section",
                content=content,
                start_line=start,
                end_line=end,
            )
        )
    return chunks
