"""In-memory indexing and issue-context retrieval."""

from pathlib import Path

from repopilot.config import Settings
from repopilot.domain import (
    AnalysisResult,
    CodeChunk,
    IndexNotReadyError,
    IndexSummary,
    ScoredChunk,
)
from repopilot.ingestion import scan_repository
from repopilot.parsing import parse_markdown, parse_python
from repopilot.retrieval import KeywordRetriever, Retriever


class RepoPilotService:
    def __init__(self, settings: Settings, retriever: Retriever | None = None) -> None:
        self.settings = settings
        self.retriever = retriever or KeywordRetriever()
        self._chunks: list[CodeChunk] | None = None

    def index(self, path: Path) -> IndexSummary:
        scan = scan_repository(path, self.settings.allowed_root, self.settings.max_file_bytes)
        chunks: list[CodeChunk] = []
        skipped = list(scan.skipped_files)
        indexed = 0
        for file in scan.files:
            try:
                parsed = (
                    parse_python(file, scan.repository)
                    if file.relative_path.lower().endswith(".py")
                    else parse_markdown(file, scan.repository)
                )
            except (SyntaxError, ValueError) as exc:
                skipped.append(f"{file.relative_path}: {type(exc).__name__}")
                continue
            chunks.extend(parsed)
            indexed += 1
        self._chunks = chunks
        return IndexSummary(
            repository=scan.repository,
            files_indexed=indexed,
            chunks_created=len(chunks),
            skipped_files=skipped,
        )

    def search(self, query: str, top_k: int) -> list[ScoredChunk]:
        if self._chunks is None:
            raise IndexNotReadyError("Index a repository before searching")
        return self.retriever.search(query, self._chunks, top_k)

    def analyze(self, issue_text: str, top_k: int) -> AnalysisResult:
        matches = self.search(issue_text, top_k)
        return AnalysisResult(
            query=issue_text,
            relevant_files=list(dict.fromkeys(item.chunk.file_path for item in matches)),
            relevant_symbols=list(
                dict.fromkeys(
                    item.chunk.symbol_name
                    for item in matches
                    if item.chunk.symbol_name and item.chunk.symbol_type != "module"
                )
            ),
            retrieved_chunks=matches,
        )
