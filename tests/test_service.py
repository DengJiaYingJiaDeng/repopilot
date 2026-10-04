from pathlib import Path

from repopilot.config import Settings
from repopilot.service import RepoPilotService


def test_index_skips_invalid_python_and_accepts_uppercase_suffix(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "valid.PY").write_text("def useful_function():\n    return 1\n")
    (repo / "invalid.py").write_text("def broken(:\n")
    service = RepoPilotService(Settings(allowed_root=tmp_path))
    summary = service.index(repo)
    assert summary.files_indexed == 1
    assert any("invalid.py: SyntaxError" in item for item in summary.skipped_files)
    assert service.search("useful function", 1)[0].chunk.symbol_name == "useful_function"


def test_reindex_replaces_previous_corpus(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "alpha.py").write_text("def rarealpha():\n    return 1\n")
    (second / "beta.py").write_text("def rarebeta():\n    return 2\n")
    service = RepoPilotService(Settings(allowed_root=tmp_path))
    service.index(first)
    assert service.search("rarealpha", 1)
    service.index(second)
    assert not service.search("rarealpha", 1)
    assert service.search("rarebeta", 1)[0].chunk.file_path == "beta.py"
