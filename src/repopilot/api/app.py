"""FastAPI endpoints for local repository investigation."""

from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from repopilot.config import Settings
from repopilot.domain import (
    AnalysisResult,
    IndexNotReadyError,
    IndexSummary,
    RepositoryError,
    ScoredChunk,
)
from repopilot.service import RepoPilotService


class IndexRequest(BaseModel):
    path: Path


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)


class AnalyzeRequest(BaseModel):
    issue_text: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)


def get_service(request: Request) -> RepoPilotService:
    service: RepoPilotService = request.app.state.service
    return service


Service = Annotated[RepoPilotService, Depends(get_service)]


def create_app(settings: Settings | None = None) -> FastAPI:
    application = FastAPI(title="RepoPilot", version="0.1.0")
    application.state.service = RepoPilotService(settings or Settings())

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/repositories/index", response_model=IndexSummary)
    def index_repository(body: IndexRequest, service: Service) -> IndexSummary:
        try:
            return service.index(body.path)
        except RepositoryError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @application.post("/search", response_model=list[ScoredChunk])
    def search(body: SearchRequest, service: Service) -> list[ScoredChunk]:
        try:
            return service.search(body.query, body.top_k)
        except IndexNotReadyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.post("/analyze", response_model=AnalysisResult)
    def analyze(body: AnalyzeRequest, service: Service) -> AnalysisResult:
        try:
            return service.analyze(body.issue_text, body.top_k)
        except IndexNotReadyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return application


app = create_app()
