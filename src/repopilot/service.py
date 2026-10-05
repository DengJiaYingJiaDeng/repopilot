"""In-memory indexing and issue-context retrieval."""

from pathlib import Path

from repopilot.callgraph import CallSite, index_calls
from repopilot.config import Settings
from repopilot.domain import (
    AnalysisResult,
    CodeChunk,
    IndexNotReadyError,
    IndexSummary,
    ScoredChunk,
)
from repopilot.embeddings import Embedder, LocalEmbedder, OpenAIEmbedder
from repopilot.ingestion import scan_repository
from repopilot.parsing import parse_markdown, parse_python
from repopilot.reranking import CrossEncoderReranker, RerankedRetriever
from repopilot.retrieval import (
    BM25Retriever,
    HybridRetriever,
    KeywordRetriever,
    Retriever,
    VectorRetriever,
)
from repopilot.symbol_sites import index_symbol_sites


class RepoPilotService:
    def __init__(
        self,
        settings: Settings,
        retrievers: dict[str, Retriever] | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self.settings = settings
        self.retrievers = (
            retrievers
            if retrievers is not None
            else {
                "keyword": KeywordRetriever(),
                "bm25": BM25Retriever(),
            }
        )
        if embedder is None and settings.embedding_provider == "local":
            model = settings.embedding_model or "sentence-transformers/all-MiniLM-L6-v2"
            embedder = LocalEmbedder(model)
        elif embedder is None and settings.embedding_provider == "openai":
            key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else ""
            embedder = OpenAIEmbedder(key, settings.embedding_model or "text-embedding-3-small")
        if embedder is not None:
            vector = VectorRetriever(embedder)
            lexical = self.retrievers.get("bm25") or BM25Retriever()
            self.retrievers["bm25"] = lexical
            self.retrievers["vector"] = vector
            self.retrievers["hybrid"] = HybridRetriever(lexical, vector)
        if settings.rerank_model:
            first_stage = self.retrievers.get("hybrid") or self.retrievers["bm25"]
            self.retrievers["rerank"] = RerankedRetriever(
                first_stage,
                CrossEncoderReranker(settings.rerank_model),
                settings.rerank_candidates,
            )
        self._index_targets = (
            [
                retriever
                for name, retriever in self.retrievers.items()
                if name in {"keyword", "hybrid"}
            ]
            if embedder is not None
            else [retriever for name, retriever in self.retrievers.items() if name != "rerank"]
        )
        self._indexed_files: dict[str, str] = {}
        self._chunks: list[CodeChunk] = []
        self._indexed = False
        self._call_sites: dict[str, list[CallSite]] = {}
        self._symbol_sites: dict[str, list[CodeChunk]] = {}

    def index(self, path: Path) -> IndexSummary:
        scan = scan_repository(path, self.settings.allowed_root, self.settings.max_file_bytes)
        chunks: list[CodeChunk] = []
        skipped = list(scan.skipped_files)
        indexed = 0
        indexed_files: dict[str, str] = {}
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
            indexed_files[file.relative_path] = file.content
            indexed += 1
        self._indexed = False
        for retriever in self._index_targets:
            retriever.index(chunks)
        self._call_sites = index_calls(indexed_files)
        self._symbol_sites = index_symbol_sites(indexed_files, scan.repository)
        self._indexed_files = indexed_files
        self._chunks = chunks
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

    @property
    def indexed_files(self) -> frozenset[str]:
        return frozenset(self._indexed_files)

    def read_file(self, path: str) -> str:
        """Read only content captured at indexing time, never arbitrary disk paths."""
        if not self._indexed:
            raise IndexNotReadyError("Index a repository before reading files")
        try:
            return self._indexed_files[path]
        except KeyError as exc:
            raise ValueError("File is not in the indexed snapshot") from exc

    def find_symbol(self, name: str, top_k: int = 10) -> list[ScoredChunk]:
        """Find named functions, classes, assignments, and imports in the snapshot."""
        if not self._indexed:
            raise IndexNotReadyError("Index a repository before finding symbols")
        query = name.casefold()
        matches = [
            ScoredChunk(
                chunk=chunk,
                score=(
                    3.0
                    if chunk.symbol_name
                    and (
                        chunk.symbol_name.casefold() == query
                        or chunk.symbol_name.casefold().endswith("." + query)
                    )
                    else 1.0
                ),
            )
            for chunk in self._chunks
            if chunk.symbol_type in {"class", "function", "async_function"}
            and chunk.symbol_name
            and query in chunk.symbol_name.casefold()
        ]
        for site in self._symbol_sites.get(name.rsplit(".", 1)[-1].casefold(), []):
            matches.append(
                ScoredChunk(chunk=site, score=2.5 if site.symbol_type == "assignment" else 2.0)
            )
        matches.sort(
            key=lambda item: (
                -item.score,
                any(
                    part == "tests" or part.startswith("test_")
                    for part in item.chunk.file_path.split("/")
                ),
                item.chunk.file_path,
                item.chunk.start_line,
            )
        )
        return matches[:top_k]

    def find_callers(self, name: str, top_k: int = 10) -> list[CallSite]:
        """Return possible callers by final identifier; not full name resolution."""
        if not self._indexed:
            raise IndexNotReadyError("Index a repository before finding callers")
        candidates = self._call_sites.get(name.rsplit(".", 1)[-1], [])
        ranked = sorted(
            candidates,
            key=lambda c: (
                any(
                    p in {"test", "tests"} or p.startswith("test_") for p in c.file_path.split("/")
                ),
                c.file_path,
                c.call_line,
            ),
        )
        return ranked[:top_k]
