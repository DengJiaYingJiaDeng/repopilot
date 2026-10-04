"""File-level retrieval evaluation against curated issue labels."""

import argparse
import json
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from repopilot.config import Settings
from repopilot.service import RepoPilotService


class IssueCase(BaseModel):
    issue_id: str = Field(min_length=1)
    issue_text: str = Field(min_length=1)
    relevant_files: list[str] = Field(min_length=1)

    @field_validator("relevant_files")
    @classmethod
    def relative_files(cls, files: list[str]) -> list[str]:
        for name in files:
            path = Path(name)
            if not name or path.is_absolute() or ".." in path.parts:
                raise ValueError("relevant_files must be repository-relative paths")
        return files


class CaseScore(BaseModel):
    issue_id: str
    recall_at_k: float
    reciprocal_rank: float
    predicted_files: list[str]
    relevant_files: list[str]


class EvaluationReport(BaseModel):
    method: str
    top_k: int
    case_count: int
    mean_recall_at_k: float
    mrr_at_k: float
    cases: list[CaseScore]


def load_cases(path: Path) -> list[IssueCase]:
    """Load one JSON object per line; reject duplicate issue IDs."""
    cases: list[IssueCase] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                case = IssueCase.model_validate_json(line)
            except ValueError as exc:
                raise ValueError(f"Invalid case at line {line_number}: {exc}") from exc
            if case.issue_id in seen:
                raise ValueError(f"Duplicate issue_id: {case.issue_id}")
            seen.add(case.issue_id)
            cases.append(case)
    if not cases:
        raise ValueError("Evaluation dataset is empty")
    return cases


def score_files(
    issue_id: str, predicted_files: list[str], relevant_files: list[str], top_k: int
) -> CaseScore:
    """Score unique file paths; a relevant file ranks at its first appearance."""
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    ranked = list(dict.fromkeys(predicted_files))[:top_k]
    relevant = set(relevant_files)
    recall = len(relevant.intersection(ranked)) / len(relevant)
    first_rank = next((rank for rank, name in enumerate(ranked, 1) if name in relevant), None)
    return CaseScore(
        issue_id=issue_id,
        recall_at_k=recall,
        reciprocal_rank=1 / first_rank if first_rank is not None else 0.0,
        predicted_files=ranked,
        relevant_files=relevant_files,
    )


def evaluate(
    service: RepoPilotService, cases: list[IssueCase], method: str, top_k: int, chunk_count: int
) -> EvaluationReport:
    """Evaluate file rankings using the same indexed repository for every case."""
    if not cases:
        raise ValueError("Evaluation dataset is empty")
    scores = []
    for case in cases:
        # Ask for all matching chunks so duplicate symbols do not consume file-level K.
        matches = service.search(case.issue_text, chunk_count, method)
        scores.append(
            score_files(
                case.issue_id,
                [item.chunk.file_path for item in matches],
                case.relevant_files,
                top_k,
            )
        )
    return EvaluationReport(
        method=method,
        top_k=top_k,
        case_count=len(scores),
        mean_recall_at_k=sum(item.recall_at_k for item in scores) / len(scores),
        mrr_at_k=sum(item.reciprocal_rank for item in scores) / len(scores),
        cases=scores,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate repository file retrieval")
    parser.add_argument("repository", type=Path)
    parser.add_argument("dataset", type=Path, help="Curated JSONL issue cases")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--methods", nargs="+", choices=["keyword", "bm25"], default=["keyword", "bm25"]
    )
    args = parser.parse_args()
    if args.top_k <= 0:
        parser.error("--top-k must be positive")
    cases = load_cases(args.dataset)
    repository = args.repository.resolve(strict=True)
    service = RepoPilotService(Settings(allowed_root=repository.parent))
    summary = service.index(repository)
    reports = [
        evaluate(service, cases, method, args.top_k, summary.chunks_created)
        for method in args.methods
    ]
    print(json.dumps([report.model_dump() for report in reports], indent=2))


if __name__ == "__main__":
    main()
