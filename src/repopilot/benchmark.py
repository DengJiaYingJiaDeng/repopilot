"""Compare paired investigation runs without pretending to grade causal correctness."""

import argparse
import json
from pathlib import Path
from statistics import median
from typing import Any


def compare_runs(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    for key in ("dataset_sha256", "model", "settings"):
        if before.get(key) != after.get(key):
            raise ValueError(f"Cannot compare runs with different {key}")
    indexed: list[dict[str, Any]] = []
    for run in (before, after):
        records = run.get("records", [])
        if not records:
            raise ValueError("Cannot compare an empty run")
        by_id = {record["issue_id"]: record for record in records}
        if len(by_id) != len(records):
            raise ValueError("Duplicate issue IDs in run")
        indexed.append(by_id)
    old, new = indexed
    if old.keys() != new.keys():
        raise ValueError("Both runs must include the same cases, including failures")
    for key in old:
        if (old[key]["repository"], old[key]["revision"]) != (
            new[key]["repository"],
            new[key]["revision"],
        ):
            raise ValueError(f"Mismatched repository revision for {key}")

    def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
        count = len(records)
        has_checks = all("evidence_status" in record["result"] for record in records)
        citations = [c for record in records for c in record["result"].get("citations", [])]
        return {
            "cases": count,
            "protocol_complete": sum(r["result"]["status"] == "complete" for r in records),
            "reports_with_verified_ranges": (
                sum(r["result"].get("evidence_status") == "verified" for r in records)
                if has_checks
                else None
            ),
            "verified_citations": sum(c["verified"] for c in citations) if has_checks else None,
            "total_citations": len(citations) if has_checks else None,
            "mean_initial_file_recall_at_3": sum(r["initial_recall_at_3"] for r in records) / count,
            "mean_cited_file_recall_at_3": sum(r["cited_recall_at_3"] for r in records) / count,
            "median_seconds": median(r["elapsed_seconds"] for r in records),
            "mean_tool_calls": sum(len(r["result"]["tool_trace"]) for r in records) / count,
        }

    return {
        "scope": "Paired development runs; source-range checks are not root-cause accuracy.",
        "before": summarize(list(old.values())),
        "after": summarize(list(new.values())),
        "cases": [
            {
                "issue_id": key,
                "before_status": old[key]["result"]["status"],
                "after_status": new[key]["result"]["status"],
                "after_evidence": new[key]["result"].get("evidence_status", "unchecked"),
                "after_checks": new[key]["result"].get("evidence_checks", []),
            }
            for key in old
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = compare_runs(json.loads(args.before.read_text()), json.loads(args.after.read_text()))
    output = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(output)
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
