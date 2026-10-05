import hashlib
import json

import pytest

from scripts.compare_read_coverage import compare_read_coverage


def test_read_coverage_counts_only_successful_complete_observations() -> None:
    dataset = (
        json.dumps(
            {
                "issue_id": "sample",
                "repository": "example/repo",
                "revision": "abc",
                "relevant_files": ["a.py", "b.py"],
            }
        )
        + "\n"
    ).encode()
    run = {
        "dataset_sha256": hashlib.sha256(dataset).hexdigest(),
        "source_digest": "implementation",
        "records": [
            {
                "issue_id": "sample",
                "repository": "example/repo",
                "revision": "abc",
                "result": {
                    "tool_trace": [
                        {
                            "name": "read_file",
                            "returned_error": False,
                            "observed_ranges": [
                                {"file_path": "a.py", "start_line": 1, "end_line": 2}
                            ],
                        },
                        {
                            "name": "read_file",
                            "returned_error": False,
                            "observed_ranges": [
                                {"file_path": "b.py", "start_line": 1, "end_line": 0}
                            ],
                        },
                        {
                            "name": "read_file",
                            "returned_error": True,
                            "observed_ranges": [
                                {"file_path": "b.py", "start_line": 1, "end_line": 2}
                            ],
                        },
                    ]
                },
            }
        ],
    }
    result = compare_read_coverage(dataset, [run])
    assert result["runs"][0]["mean_read_recall_at_3"] == 0.5
    assert result["runs"][0]["cases"][0]["read_files"] == ["a.py"]
    with pytest.raises(ValueError, match="different dataset"):
        compare_read_coverage(dataset, [{**run, "dataset_sha256": "wrong"}])
