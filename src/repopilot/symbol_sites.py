"""AST locations for Python value writes and imports in the indexed snapshot."""

import ast
import hashlib
from collections import defaultdict
from typing import Literal

from repopilot.domain import CodeChunk


def index_symbol_sites(files: dict[str, str], repository: str) -> dict[str, list[CodeChunk]]:
    sites: dict[str, list[CodeChunk]] = defaultdict(list)
    for path, source in sorted(files.items()):
        if not path.lower().endswith(".py"):
            continue
        tree = ast.parse(source, filename=path)
        lines = source.splitlines(keepends=True)

        def add(
            name: str,
            node: ast.stmt,
            scope: tuple[str, ...],
            kind: Literal["assignment", "import"],
            path: str = path,
            lines: list[str] = lines,
        ) -> None:
            start = node.lineno
            end = node.end_lineno or start
            qualified = ".".join((*scope, name))
            identity = f"{path}:{kind}:{start}:{qualified}"
            sites[name.casefold()].append(
                CodeChunk(
                    id=hashlib.sha256(identity.encode()).hexdigest()[:20],
                    repository=repository,
                    file_path=path,
                    language="python",
                    symbol_name=qualified,
                    symbol_type=kind,
                    content="".join(lines[start - 1 : end]),
                    start_line=start,
                    end_line=end,
                    parent_symbol=".".join(scope) or None,
                )
            )

        def names(target: ast.expr) -> list[str]:
            if isinstance(target, ast.Name):
                return [target.id]
            if isinstance(target, ast.Attribute):
                return [target.attr]
            if isinstance(target, (ast.Tuple, ast.List)):
                return [name for item in target.elts for name in names(item)]
            return []

        def visit(node: ast.AST, scope: tuple[str, ...]) -> None:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                scope = (*scope, node.name)
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    for name in names(target):
                        add(name, node, scope, "assignment")
            elif isinstance(node, ast.AnnAssign):
                for name in names(node.target):
                    add(name, node, scope, "assignment")
            elif isinstance(node, ast.AugAssign):
                for name in names(node.target):
                    add(name, node, scope, "assignment")
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    add(alias.asname or alias.name.split(".", 1)[0], node, scope, "import")
            for child in ast.iter_child_nodes(node):
                visit(child, scope)

        visit(tree, ())
    return dict(sites)
