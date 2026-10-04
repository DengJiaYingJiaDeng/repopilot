"""Optional LangGraph orchestration for retrieval, investigation, and review routing."""

from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from repopilot.agent import InvestigationResult, Investigator
from repopilot.domain import AnalysisResult


class InvestigationState(TypedDict, total=False):
    issue_text: str
    response_language: Literal["en", "zh"]
    method: str
    initial_context: AnalysisResult
    result: InvestigationResult
    review_required: bool


def build_investigation_graph(investigator: Investigator) -> Any:
    """Route incomplete or insufficiently grounded investigations for review."""

    def retrieve(state: InvestigationState) -> InvestigationState:
        return {
            "initial_context": investigator.service.analyze(
                state["issue_text"], 5, state.get("method", "bm25")
            )
        }

    def investigate(state: InvestigationState) -> InvestigationState:
        return {
            "result": investigator.investigate(
                state["issue_text"],
                state.get("method", "bm25"),
                initial_context=state["initial_context"],
                response_language=state.get("response_language", "en"),
            )
        }

    def needs_review(state: InvestigationState) -> str:
        return (
            "review"
            if (state["result"].status == "incomplete" or state["result"].review_required)
            else "done"
        )

    def review(state: InvestigationState) -> InvestigationState:
        return {"review_required": True}

    workflow: StateGraph[InvestigationState] = StateGraph(InvestigationState)
    workflow.add_node("retrieve", retrieve)
    workflow.add_node("investigate", investigate)
    workflow.add_node("review", review)
    workflow.add_edge(START, "retrieve")
    workflow.add_edge("retrieve", "investigate")
    workflow.add_conditional_edges("investigate", needs_review, {"review": "review", "done": END})
    workflow.add_edge("review", END)
    return workflow.compile()
