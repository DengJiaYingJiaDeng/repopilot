"""Shared data models and domain errors."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SymbolType = Literal[
    "module", "class", "function", "async_function", "markdown_section", "assignment", "import"
]


class CodeChunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    repository: str
    file_path: str
    language: Literal["python", "markdown"]
    symbol_name: str | None = None
    symbol_type: SymbolType
    content: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    parent_symbol: str | None = None


class ScoredChunk(BaseModel):
    chunk: CodeChunk
    score: float


class IndexSummary(BaseModel):
    repository: str
    files_indexed: int
    chunks_created: int
    skipped_files: list[str]


class AnalysisResult(BaseModel):
    query: str
    relevant_files: list[str]
    relevant_symbols: list[str]
    retrieved_chunks: list[ScoredChunk]


class RepositoryError(Exception):
    """A repository cannot be indexed safely."""


class IndexNotReadyError(Exception):
    """Search was requested before indexing a repository."""


class ModelProviderError(Exception):
    """A configured model backend failed to return a usable response."""
