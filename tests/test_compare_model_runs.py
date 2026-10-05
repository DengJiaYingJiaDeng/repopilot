import runpy
from pathlib import Path

import pytest

compare_model_runs = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts" / "compare_model_runs.py")
)["compare_model_runs"]


def test_model_comparison_keeps_code_cases_and_settings_identical() -> None:
    base = {
        "dataset_sha256": "dataset",
        "source_digest": "code",
        "settings": {"method": "bm25"},
        "model": "small",
        "records": [
            {
                "issue_id": "one",
                "repository": "org/repo",
                "revision": "sha",
                "initial_recall_at_3": 0.5,
                "cited_recall_at_3": 0.0,
                "elapsed_seconds": 2.0,
                "result": {"status": "complete", "evidence_status": "verified", "tool_trace": []},
            }
        ],
    }
    other = {**base, "model": "large"}
    result = compare_model_runs(base, other)
    assert [item["model"] for item in result["runs"]] == ["small", "large"]
    with pytest.raises(ValueError, match="source_digest"):
        compare_model_runs(base, {**other, "source_digest": "different"})
    with pytest.raises(ValueError, match="different repository revisions"):
        compare_model_runs(
            base,
            {**other, "records": [{**other["records"][0], "revision": "other"}]},
        )
