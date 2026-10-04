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
from repopilot.retrieval import BM25Retriever, KeywordRetriever, Retriever


class RepoPilotService:
    def __init__(self, settings: Settings, retrievers: dict[str, Retriever] | None = None) -> None:
        self.settings = settings
        self.retrievers = retrievers or {
            "keyword": KeywordRetriever(),
            "bm25": BM25Retriever(),
        }
        self._indexed = False

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
        for retriever in self.retrievers.values():
            retriever.index(chunks)
        self._indexed = True
        return IndexSummary(
            repository=scan.repository,
            files_indexed=indexed,
            chunks_created=len(chunks),
            skipped_files=skipped,
        )

    def search(self, query: str, top_k: int, method: str = "keyword") -> list[ScoredChunk]:
        if not self._indexed:
            raise IndexNotReadyError("Index a repository before searching")
        try:
            retriever = self.retrievers[method]
        except KeyError as exc:
            raise ValueError(f"Unknown retrieval method: {method}") from exc
        return retriever.search(query, top_k)

    def analyze(self, issue_text: str, top_k: int, method: str = "keyword") -> AnalysisResult:
        matches = self.search(issue_text, top_k, method)
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
