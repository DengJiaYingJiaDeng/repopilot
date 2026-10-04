"""FastAPI endpoints for local repository investigation."""

from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from repopilot.agent import InvestigationResult, Investigator, OpenAIInvestigationModel
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
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=50)
    method: Literal["keyword", "bm25", "vector", "hybrid", "rerank"] = "keyword"


class InvestigateRequest(BaseModel):
    issue_text: str = Field(min_length=1, max_length=4000)
    method: Literal["keyword", "bm25", "vector", "hybrid", "rerank"] = "bm25"


class AnalyzeRequest(BaseModel):
    issue_text: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=50)
    method: Literal["keyword", "bm25", "vector", "hybrid", "rerank"] = "keyword"


def get_service(request: Request) -> RepoPilotService:
    service: RepoPilotService = request.app.state.service
    return service


Service = Annotated[RepoPilotService, Depends(get_service)]


def create_app(settings: Settings | None = None) -> FastAPI:
    application = FastAPI(title="RepoPilot", version="0.6.0")
    config = settings or Settings()
    application.state.service = RepoPilotService(config)
    application.state.investigator = None
    application.state.investigation_graph = None
    if config.investigation_model:
        key = config.openai_api_key.get_secret_value() if config.openai_api_key else ""
        application.state.investigator = Investigator(
            application.state.service,
            OpenAIInvestigationModel(key, config.investigation_model),
            config.max_agent_calls,
        )
        if config.investigation_workflow == "langgraph":
            from repopilot.graph_workflow import build_investigation_graph

            application.state.investigation_graph = build_investigation_graph(
                application.state.investigator
            )

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
            return service.search(body.query, body.top_k, body.method)
        except IndexNotReadyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @application.post("/analyze", response_model=AnalysisResult)
    def analyze(body: AnalyzeRequest, service: Service) -> AnalysisResult:
        try:
            return service.analyze(body.issue_text, body.top_k, body.method)
        except IndexNotReadyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @application.post("/investigate", response_model=InvestigationResult)
    def investigate(body: InvestigateRequest, request: Request) -> InvestigationResult:
        investigator: Investigator | None = request.app.state.investigator
        if investigator is None:
            raise HTTPException(status_code=503, detail="Investigation model is not configured")
        try:
            graph = request.app.state.investigation_graph
            if graph is not None:
                state = graph.invoke({"issue_text": body.issue_text, "method": body.method})
                result: InvestigationResult = state["result"]
                return result.model_copy(
                    update={"review_required": state.get("review_required", False)}
                )
            return investigator.investigate(body.issue_text, body.method)
        except IndexNotReadyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return application


app = create_app()
