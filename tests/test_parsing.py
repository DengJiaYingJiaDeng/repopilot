from repopilot.ingestion import SourceFile
from repopilot.parsing import parse_markdown, parse_python


def test_python_ast_extracts_nested_symbols_and_lines() -> None:
    source = SourceFile(
        "app.py",
        "def top():\n"
        "    return 1\n"
        "\n"
        "class Worker:\n"
        "    async def run(self):\n"
        "        return top()\n",
    )
    chunks = parse_python(source, "repo")
    by_name = {chunk.symbol_name: chunk for chunk in chunks}
    assert by_name["top"].symbol_type == "function"
    assert by_name["top"].start_line == 1
    assert by_name["top"].end_line == 2
    assert by_name["Worker"].symbol_type == "class"
    assert by_name["Worker.run"].symbol_type == "async_function"
    assert by_name["Worker.run"].parent_symbol == "Worker"
    assert "return top()" in by_name["Worker.run"].content


def test_markdown_sections_keep_line_ranges() -> None:
    chunks = parse_markdown(SourceFile("README.md", "Intro\n# Setup\nInstall\n## Run\nGo\n"), "r")
    assert [(chunk.symbol_name, chunk.start_line, chunk.end_line) for chunk in chunks] == [
        ("README.md", 1, 1),
        ("Setup", 2, 3),
        ("Run", 4, 5),
    ]
