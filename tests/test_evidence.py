import json
from pathlib import Path

import pytest
from test_agent import FakeModel, indexed_service

from repopilot.agent import Investigator, ModelTurn, ToolTrace
from repopilot.evidence import Citation, assess_evidence


def read_trace(investigator: Investigator, path: str, start: int, end: int) -> ToolTrace:
    args, output = investigator._run_tool(
        "read_file", json.dumps({"path": path, "start_line": start, "end_line": end})
    )
    return ToolTrace(name="read_file", arguments=args, output=output)


def test_validates_only_lines_actually_returned_by_read_tool(tmp_path: Path) -> None:
    service = indexed_service(tmp_path)
    investigator = Investigator(service, FakeModel([]))
    citation = Citation(file_path="config.py", start_line=1, end_line=2, reason="Constant return")
    trace = [read_trace(investigator, "config.py", 1, 2)]
    result = assess_evidence(service, [citation], ["config.py"], trace)
    assert result.status == "verified"
    assert result.successful_reads == 1
    assert "return 'setting'" in result.citations[0].content
    # Reading only the function header cannot support an unseen body line.
    partial = assess_evidence(
        service, [citation], ["config.py"], [read_trace(investigator, "config.py", 1, 1)]
    )
    assert partial.status == "insufficient"
    assert "citation_not_read" in partial.checks
    assert partial.citations[0].content == ""


@pytest.mark.parametrize(
    "start,end,problem",
    [(2, 1, "invalid_line_range"), (1, 999, "invalid_line_range"), (2, 2, "citation_not_read")],
)
def test_rejects_invalid_or_unread_citations(
    tmp_path: Path, start: int, end: int, problem: str
) -> None:
    service = indexed_service(tmp_path)
    result = assess_evidence(
        service,
        [Citation(file_path="config.py", start_line=start, end_line=end, reason="Claim")],
        ["config.py"],
        [],
    )
    assert problem in result.checks
    assert result.status == "insufficient"


def test_search_results_and_failed_reads_do_not_verify_a_citation(tmp_path: Path) -> None:
    service = indexed_service(tmp_path)
    agent = Investigator(service, FakeModel([]))
    args, output = agent._run_tool("find_symbol", '{"name":"load_config"}')
    trace = [
        ToolTrace(name="find_symbol", arguments=args, output=output),
        read_trace(agent, "config.py", 99, 100),
    ]
    citation = Citation(file_path="config.py", start_line=1, end_line=2, reason="Claim")
    assert assess_evidence(service, [citation], ["config.py"], trace).status == "insufficient"


def test_partial_truncated_line_is_not_counted_as_read(tmp_path: Path) -> None:
    service = indexed_service(tmp_path)
    path = tmp_path / "repo" / "long.py"
    path.write_text('def long_value():\n    return "' + "x" * 9000 + '"\n')
    service.index(path.parent)
    agent = Investigator(service, FakeModel([]))
    trace = [read_trace(agent, "long.py", 1, 2)]
    citation = Citation(file_path="long.py", start_line=2, end_line=2, reason="Long value")
    result = assess_evidence(service, [citation], ["long.py"], trace)
    assert result.successful_reads == 1
    assert "citation_not_read" in result.checks


def test_legacy_answer_retained_but_requires_evidence_review(tmp_path: Path) -> None:
    answer = json.dumps(
        {
            "root_cause_hypothesis": "Unknown",
            "investigation_steps": ["Inspect"],
            "test_plan": ["Test"],
            "evidence_files": ["config.py"],
        }
    )
    result = Investigator(
        indexed_service(tmp_path), FakeModel([ModelTurn("1", [], answer)])
    ).investigate("config")
    assert result.status == "complete"
    assert result.review_required
    assert result.evidence_status == "insufficient"
    assert "missing_citations" in result.evidence_checks


def test_all_listed_files_need_citations_and_tests_do_not_establish_implementation(
    tmp_path: Path,
) -> None:
    service = indexed_service(tmp_path)
    path = tmp_path / "repo" / "test_config.py"
    path.write_text("def test_load():\n    assert True\n")
    service.index(path.parent)
    agent = Investigator(service, FakeModel([]))
    trace = [read_trace(agent, "test_config.py", 1, 2)]
    citation = Citation(file_path="test_config.py", start_line=1, end_line=2, reason="Only a test")
    result = assess_evidence(service, [citation], ["test_config.py", "config.py"], trace)
    assert "uncited_evidence_file" in result.checks
    assert "no_implementation_citation" in result.checks
