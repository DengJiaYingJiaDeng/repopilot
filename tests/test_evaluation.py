from pathlib import Path

import pytest

from repopilot.config import Settings
from repopilot.evaluation import IssueCase, evaluate, load_cases, score_files
from repopilot.service import RepoPilotService

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


def test_file_level_metrics_deduplicate_chunk_hits() -> None:
    result = score_files("issue-1", ["a.py", "a.py", "b.py"], ["b.py", "c.py"], 2)
    assert result.predicted_files == ["a.py", "b.py"]
    assert result.recall_at_k == 0.5
    assert result.reciprocal_rank == 0.5


def test_evaluation_runs_both_methods_on_same_repository() -> None:
    service = RepoPilotService(Settings(allowed_root=FIXTURE.parent))
    summary = service.index(FIXTURE)
    cases = [
        IssueCase(
            issue_id="config",
            issue_text="environment config",
            relevant_files=["config.py"],
        ),
        IssueCase(
            issue_id="startup",
            issue_text="MCP server startup",
            relevant_files=["mcp_server.py"],
        ),
    ]
    for method in ("keyword", "bm25"):
        report = evaluate(service, cases, method, top_k=3, chunk_count=summary.chunks_created)
        assert report.case_count == 2
        assert 0 <= report.mean_recall_at_k <= 1
        assert 0 <= report.mrr_at_k <= 1
        assert all(len(case.predicted_files) <= 3 for case in report.cases)


def test_dataset_loader_rejects_duplicate_ids_and_unsafe_paths(tmp_path: Path) -> None:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        '{"issue_id":"one","issue_text":"bug","relevant_files":["src/a.py"]}\n'
        '{"issue_id":"one","issue_text":"bug","relevant_files":["src/b.py"]}\n'
    )
    with pytest.raises(ValueError, match="Duplicate issue_id"):
        load_cases(dataset)
    with pytest.raises(ValueError, match="repository-relative"):
        IssueCase(issue_id="unsafe", issue_text="bug", relevant_files=["../secret.py"])
