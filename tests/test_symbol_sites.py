from pathlib import Path

from repopilot.config import Settings
from repopilot.service import RepoPilotService


def test_find_symbol_locates_value_definitions_and_imports(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "_internal_utils.py").write_text(
        'HEADER_VALIDATORS = {"name": r"^[^\\n]+$"}\n# PHANTOM = 1\ntext = "GHOST = 2"\n'
    )
    (repo / "utils.py").write_text(
        "from ._internal_utils import HEADER_VALIDATORS\n"
        "def check():\n"
        "    return HEADER_VALIDATORS\n"
    )
    (repo / "models.py").write_text(
        "class PreparedRequest:\n"
        "    def prepare_body(self, body):\n"
        "        self._body_position = body.tell()\n"
    )
    service = RepoPilotService(Settings(allowed_root=tmp_path))
    service.index(repo)
    found = service.find_symbol("HEADER_VALIDATORS")
    assert [(item.chunk.file_path, item.chunk.symbol_type) for item in found[:2]] == [
        ("_internal_utils.py", "assignment"),
        ("utils.py", "import"),
    ]
    position = service.find_symbol("_body_position")
    assert position[0].chunk.file_path == "models.py"
    assert position[0].chunk.symbol_name == "PreparedRequest.prepare_body._body_position"
    assert position[0].chunk.start_line == 3
    assert service.find_symbol("self._body_position")[0].chunk.file_path == "models.py"
    assert service.find_symbol("header_validators")[0].chunk.file_path == "_internal_utils.py"
    assert service.find_symbol("PHANTOM") == []
    assert service.find_symbol("GHOST") == []
    assert service.find_symbol("prepare_body")[0].chunk.symbol_type == "function"


def test_symbol_sites_are_replaced_with_new_snapshot(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "a.py").write_text("TARGET = 1\n")
    (second / "b.py").write_text("OTHER = 2\n")
    service = RepoPilotService(Settings(allowed_root=tmp_path))
    service.index(first)
    assert service.find_symbol("TARGET")
    service.index(second)
    assert service.find_symbol("TARGET") == []
    assert service.find_symbol("OTHER")[0].chunk.file_path == "b.py"
