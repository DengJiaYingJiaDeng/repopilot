"""Read allowed source files from a local directory."""

import os
from dataclasses import dataclass
from pathlib import Path

from repopilot.domain import RepositoryError

IGNORED_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "dist",
        "build",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "coverage",
    }
)
ALLOWED_SUFFIXES = frozenset({".py", ".md"})


@dataclass(frozen=True)
class SourceFile:
    relative_path: str
    content: str


@dataclass(frozen=True)
class ScanResult:
    repository: str
    files: list[SourceFile]
    skipped_files: list[str]


def scan_repository(path: Path, allowed_root: Path, max_file_bytes: int) -> ScanResult:
    """Scan a repository without following symlinks or crossing the allowed root."""
    try:
        root = path.expanduser().resolve(strict=True)
        boundary = allowed_root.expanduser().resolve(strict=True)
    except OSError as exc:
        raise RepositoryError(f"Repository or allowed root does not exist: {exc}") from exc

    if not root.is_dir():
        raise RepositoryError("Repository path must be a directory")
    if not root.is_relative_to(boundary):
        raise RepositoryError("Repository path is outside REPOPILOT_ALLOWED_ROOT")

    files: list[SourceFile] = []
    skipped: list[str] = []

    def on_walk_error(error: OSError) -> None:
        skipped.append(f"{error.filename}: {error.strerror}")

    for directory, dirs, names in os.walk(root, followlinks=False, onerror=on_walk_error):
        current = Path(directory)
        dirs[:] = sorted(
            name for name in dirs if name not in IGNORED_DIRS and not (current / name).is_symlink()
        )
        for name in sorted(names):
            file_path = current / name
            if file_path.suffix.lower() not in ALLOWED_SUFFIXES:
                continue
            relative = file_path.relative_to(root).as_posix()
            try:
                if file_path.is_symlink():
                    skipped.append(f"{relative}: symlink")
                    continue
                if file_path.stat().st_size > max_file_bytes:
                    skipped.append(f"{relative}: too large")
                    continue
                with file_path.open("rb") as source:
                    data = source.read(max_file_bytes + 1)
                if len(data) > max_file_bytes:
                    skipped.append(f"{relative}: too large")
                    continue
                if b"\x00" in data:
                    skipped.append(f"{relative}: binary")
                    continue
                files.append(SourceFile(relative, data.decode("utf-8")))
            except (OSError, UnicodeDecodeError) as exc:
                skipped.append(f"{relative}: {type(exc).__name__}")

    return ScanResult(repository=root.name, files=files, skipped_files=skipped)
