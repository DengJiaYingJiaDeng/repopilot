"""Run pinned, read-only investigation cases; labels never enter the model prompt."""

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

from fastapi.testclient import TestClient

from repopilot.api.app import create_app
from repopilot.config import Settings
from repopilot.evaluation import score_files


def git_revision(path: Path) -> str:
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("checkouts", type=Path, help="JSON map: repository@sha -> local checkout")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, help="Optional full traces, never publish")
    parser.add_argument("--model-url", default="http://127.0.0.1:18081/v1")
    parser.add_argument("--model", default="qwen3-4b")
    parser.add_argument("--case", action="append", dest="selected")
    args = parser.parse_args()
    cases = [json.loads(line) for line in args.dataset.read_text().splitlines() if line.strip()]
    if len({case["issue_id"] for case in cases}) != len(cases):
        parser.error("Duplicate case IDs")
    if args.selected:
        unknown = set(args.selected) - {case["issue_id"] for case in cases}
        if unknown:
            parser.error(f"Unknown case IDs: {sorted(unknown)}")
        cases = [case for case in cases if case["issue_id"] in args.selected]
    checkouts = json.loads(args.checkouts.read_text())
    project = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for source in sorted((project / "src/repopilot").rglob("*.py")):
        digest.update(str(source.relative_to(project)).encode())
        digest.update(source.read_bytes())
    report = {
        "schema_version": 1,
        "source_commit": git_revision(project),
        "source_digest": digest.hexdigest(),
        "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        "model": args.model,
        "settings": {"method": "bm25", "max_agent_calls": 6, "response_language": "en"},
        "scope": "Manually curated development cases. No independent accuracy estimate.",
        "records": [],
    }
    if args.private_output:
        args.private_output.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for case in cases:
        repo = Path(checkouts[f"{case['repository']}@{case['revision']}"]).resolve(strict=True)
        if git_revision(repo) != case["revision"]:
            raise ValueError(f"Wrong checkout revision for {case['issue_id']}")
        if subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True):
            raise ValueError(f"Dirty benchmark checkout: {repo}")
        with TestClient(
            create_app(
                Settings(
                    allowed_root=repo.parent,
                    investigation_provider="local",
                    investigation_model=args.model,
                    local_model_url=args.model_url,
                    investigation_workflow="langgraph",
                    max_agent_calls=6,
                )
            )
        ) as client:
            indexed = client.post("/repositories/index", json={"path": str(repo)})
            indexed.raise_for_status()
            missing = set(case["relevant_files"]) - client.app.state.service.indexed_files
            if missing:
                raise ValueError(f"Labels absent from snapshot: {missing}")
            start = time.perf_counter()
            response = client.post(
                "/investigate", json={"issue_text": case["issue_text"], "method": "bm25"}
            )
            response.raise_for_status()
            result = response.json()
            elapsed = round(time.perf_counter() - start, 3)
        if args.private_output:
            name = case["issue_id"].replace("/", "_").replace("#", "-") + ".json"
            (args.private_output / name).write_text(
                json.dumps({"index": indexed.json(), "result": result}, indent=2) + "\n"
            )
        context = result.pop("initial_context")
        initial = score_files(
            case["issue_id"], context["relevant_files"], case["relevant_files"], 3
        )
        cited = score_files(case["issue_id"], result["evidence_files"], case["relevant_files"], 3)
        for trace in result["tool_trace"]:
            output = trace.pop("output")
            trace["output_characters"] = len(output)
            try:
                parsed = json.loads(output)
                trace["returned_error"] = isinstance(parsed, dict) and "error" in parsed
                # Keep paths/ranges for provenance inspection, omit upstream source excerpts.
                trace["observed_ranges"] = [
                    {k: item[k] for k in ("file_path", "start_line", "end_line") if k in item}
                    for item in (parsed if isinstance(parsed, list) else [parsed])
                    if isinstance(item, dict) and "file_path" in item
                ]
            except ValueError:
                trace["returned_error"] = True
        for citation in result.get("citations", []):
            citation.pop("content", None)
        record = {
            "issue_id": case["issue_id"],
            "repository": case["repository"],
            "revision": case["revision"],
            "elapsed_seconds": elapsed,
            "initial_recall_at_3": initial.recall_at_k,
            "cited_recall_at_3": cited.recall_at_k,
            "result": result,
        }
        report["records"].append(record)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        print(
            json.dumps(
                {
                    "case": case["issue_id"],
                    "status": result["status"],
                    "evidence": result.get("evidence_status", "legacy"),
                    "seconds": elapsed,
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
