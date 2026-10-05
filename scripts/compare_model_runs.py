"""Compare two different models on identical pinned investigation code and cases."""

import argparse
import json
from pathlib import Path
from statistics import median
from typing import Any


def compare_model_runs(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    for key in ("dataset_sha256", "source_digest", "settings"):
        if left.get(key) != right.get(key):
            raise ValueError(f"Model runs differ in {key}")
    if left.get("model") == right.get("model"):
        raise ValueError("Expected two different models")

    records: list[dict[str, dict[str, Any]]] = []
    for run in (left, right):
        items = run.get("records", [])
        by_id = {item["issue_id"]: item for item in items}
        if not items or len(by_id) != len(items):
            raise ValueError("Run is empty or has duplicate case IDs")
        records.append(by_id)
    first, second = records
    if first.keys() != second.keys():
        raise ValueError("Runs have different case sets")
    for key in first:
        if (first[key]["repository"], first[key]["revision"]) != (
            second[key]["repository"],
            second[key]["revision"],
        ):
            raise ValueError("Runs use different repository revisions")

    def summarize(run: dict[str, Any]) -> dict[str, Any]:
        items = run["records"]
        return {
            "model": run["model"],
            "cases": len(items),
            "protocol_complete": sum(x["result"]["status"] == "complete" for x in items),
            "provenance_verified": sum(
                x["result"].get("evidence_status") == "verified" for x in items
            ),
            "mean_initial_file_recall_at_3": sum(x["initial_recall_at_3"] for x in items)
            / len(items),
            "mean_cited_file_recall_at_3": sum(x["cited_recall_at_3"] for x in items) / len(items),
            "median_seconds": median(x["elapsed_seconds"] for x in items),
            "mean_tool_calls": sum(len(x["result"]["tool_trace"]) for x in items) / len(items),
        }

    return {
        "dataset_sha256": left["dataset_sha256"],
        "source_digest": left["source_digest"],
        "settings": left["settings"],
        "runs": [summarize(left), summarize(right)],
        "cases": [
            {
                "issue_id": key,
                left["model"]: {
                    "cited_recall_at_3": first[key]["cited_recall_at_3"],
                    "status": first[key]["result"]["status"],
                },
                right["model"]: {
                    "cited_recall_at_3": second[key]["cited_recall_at_3"],
                    "status": second[key]["result"]["status"],
                },
            }
            for key in first
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = compare_model_runs(
        json.loads(args.left.read_text()), json.loads(args.right.read_text())
    )
    output = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(output)
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
