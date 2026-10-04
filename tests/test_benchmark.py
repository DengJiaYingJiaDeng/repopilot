from copy import deepcopy

import pytest

from repopilot.benchmark import compare_runs


def run() -> dict:
    return {
        "dataset_sha256": "abc",
        "model": "local",
        "settings": {"method": "bm25"},
        "records": [
            {
                "issue_id": "case",
                "repository": "owner/repo",
                "revision": "pinned",
                "elapsed_seconds": 3.0,
                "initial_recall_at_3": 1.0,
                "cited_recall_at_3": 0.0,
                "result": {"status": "incomplete", "tool_trace": []},
            },
        ],
    }


def test_comparison_keeps_failures_and_legacy_checks_unavailable() -> None:
    before = run()
    after = deepcopy(before)
    after["records"][0]["result"].update(evidence_status="insufficient", citations=[])
    result = compare_runs(before, after)
    assert result["before"]["protocol_complete"] == 0
    assert result["before"]["reports_with_verified_ranges"] is None
    assert result["after"]["reports_with_verified_ranges"] == 0
    assert result["after"]["mean_cited_file_recall_at_3"] == 0


@pytest.mark.parametrize("change", ["dataset", "revision", "missing", "duplicate"])
def test_comparison_rejects_unpaired_runs(change: str) -> None:
    before = run()
    after = deepcopy(before)
    if change == "dataset":
        after["dataset_sha256"] = "different"
    elif change == "revision":
        after["records"][0]["revision"] = "fixed-version"
    elif change == "missing":
        after["records"] = []
    else:
        after["records"].append(after["records"][0])
    with pytest.raises(ValueError):
        compare_runs(before, after)
