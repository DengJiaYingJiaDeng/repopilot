"""Compare actual read_file coverage against pinned source labels, after investigations."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from repopilot.evaluation import score_files


def compare_read_coverage(dataset: bytes, runs: list[dict[str, Any]]) -> dict[str, Any]:
    cases = [json.loads(line) for line in dataset.splitlines() if line.strip()]
    labels = {case["issue_id"]: case for case in cases}
    if len(labels) != len(cases):
        raise ValueError("Duplicate dataset case IDs")
    digest = hashlib.sha256(dataset).hexdigest()
    output: dict[str, Any] = {"dataset_sha256": digest, "runs": []}
    for run in runs:
        if run.get("dataset_sha256") != digest:
            raise ValueError("Run uses a different dataset")
        records = run["records"]
        if len(records) != len(labels) or {r["issue_id"] for r in records} != set(labels):
            raise ValueError("Run must contain every dataset case exactly once")
        per_case = []
        for record in records:
            case = labels[record["issue_id"]]
            if (record["repository"], record["revision"]) != (case["repository"], case["revision"]):
                raise ValueError("Run contains a different repository revision")
            paths: list[str] = []
            for tool in record["result"]["tool_trace"]:
                if tool["name"] != "read_file" or tool.get("returned_error"):
                    continue
                for observed in tool.get("observed_ranges", []):
                    if observed.get("end_line", 0) < observed.get("start_line", 1):
                        continue
                    path = observed.get("file_path")
                    if path and path not in paths:
                        paths.append(path)
            score = score_files(case["issue_id"], paths, case["relevant_files"], 3)
            per_case.append(
                {
                    "issue_id": case["issue_id"],
                    "read_files": paths,
                    "read_recall_at_3": score.recall_at_k,
                }
            )
        output["runs"].append(
            {
                "source_digest": run["source_digest"],
                "mean_read_recall_at_3": sum(item["read_recall_at_3"] for item in per_case)
                / len(per_case),
                "cases": per_case,
            }
        )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("runs", type=Path, nargs="+")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = compare_read_coverage(
        args.dataset.read_bytes(), [json.loads(path.read_text()) for path in args.runs]
    )
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
