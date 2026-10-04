"""Record a live, sequential local-LLM run through FastAPI and LangGraph.

This checks protocol completion, not root-cause correctness. Run outside CI.
"""

import argparse
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from repopilot.api.app import create_app
from repopilot.config import Settings
from repopilot.evaluation import load_cases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    client = TestClient(
        create_app(
            Settings(
                allowed_root=repository.parent,
                investigation_provider="local",
                investigation_model="qwen3-4b",
                investigation_workflow="langgraph",
            )
        )
    )
    response = client.post("/repositories/index", json={"path": str(repository)})
    response.raise_for_status()
    records = []
    for case in load_cases(args.dataset):
        start = time.perf_counter()
        response = client.post(
            "/investigate", json={"issue_text": case.issue_text, "method": "bm25"}
        )
        response.raise_for_status()
        result = response.json()
        # Keep diagnostic summaries public without duplicating the upstream source corpus.
        result.pop("initial_context")
        for tool in result["tool_trace"]:
            output = tool.pop("output")
            tool["output_characters"] = len(output)
            tool["returned_error"] = output.startswith('{"error":')
        record = {
            "issue_id": case.issue_id,
            "elapsed_seconds": round(time.perf_counter() - start, 3),
            "result": result,
        }
        records.append(record)
        args.output.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "issue_id": case.issue_id,
                    "seconds": record["elapsed_seconds"],
                    "status": result["status"],
                    "tools": [tool["name"] for tool in result["tool_trace"]],
                    "limitation": result["limitation"],
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
