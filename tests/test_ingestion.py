from pathlib import Path

import pytest

from repopilot.domain import RepositoryError
from repopilot.ingestion import scan_repository


def test_filters_unreadable_and_ignored_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("x = 1\n")
    (repo / "README.md").write_text("# Hello\n")
    (repo / "binary.py").write_bytes(b"abc\x00def")
    (repo / "large.py").write_text("x" * 50)
    (repo / "bad.py").write_bytes(b"\xff")
    for ignored in ("node_modules", ".git"):
        directory = repo / ignored
        directory.mkdir()
        (directory / "hidden.py").write_text("x = 2\n")
    result = scan_repository(repo, tmp_path, max_file_bytes=40)
    assert {file.relative_path for file in result.files} == {"main.py", "README.md"}
    assert any("binary.py: binary" in item for item in result.skipped_files)
    assert any("large.py: too large" in item for item in result.skipped_files)
    assert any("bad.py: UnicodeDecodeError" in item for item in result.skipped_files)


def test_rejects_outside_root_and_skips_symlinks(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("secret = True\n")
    repo = allowed / "repo"
    repo.mkdir()
    (repo / "link.py").symlink_to(outside / "secret.py")
    (repo / "linked_dir").symlink_to(outside, target_is_directory=True)
    result = scan_repository(repo, allowed, max_file_bytes=100)
    assert result.files == []
    assert any("link.py: symlink" in item for item in result.skipped_files)
    with pytest.raises(RepositoryError):
        scan_repository(outside, allowed, max_file_bytes=100)
