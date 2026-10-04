"""Conservative Python call-site candidates, never a resolved runtime call graph."""

import ast
from collections import defaultdict

from pydantic import BaseModel


class CallSite(BaseModel):
    file_path: str
    caller: str
    callee: str
    call_line: int
    start_line: int
    end_line: int
    content: str
    content_truncated: bool = False
    match_kind: str = "name_candidate"
    limitation: str = (
        "Name match only; aliases, dynamic dispatch and receiver types are unresolved."
    )


def index_calls(files: dict[str, str]) -> dict[str, list[CallSite]]:
    index: dict[str, list[CallSite]] = defaultdict(list)
    for path, source in sorted(files.items()):
        if not path.endswith(".py"):
            continue
        lines = source.splitlines()
        tree = ast.parse(source, filename=path)

        def visit(
            node: ast.AST,
            scope: tuple[str, ...],
            lines: list[str] = lines,
            path: str = path,
        ) -> None:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                scope = (*scope, node.name)
            if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute)):
                name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr
                start = max(1, node.lineno - 3)
                end = min(len(lines), (node.end_lineno or node.lineno) + 3, start + 19)
                index[name].append(
                    CallSite(
                        file_path=path,
                        caller=".".join(scope) or "<module>",
                        callee=ast.unparse(node.func)[:200],
                        call_line=node.lineno,
                        start_line=start,
                        end_line=end,
                        content="\n".join(lines[start - 1 : end])[:2000],
                        content_truncated=len("\n".join(lines[start - 1 : end])) > 2000,
                    )
                )
            for child in ast.iter_child_nodes(node):
                visit(child, scope)

        visit(tree, ())
    return dict(index)
