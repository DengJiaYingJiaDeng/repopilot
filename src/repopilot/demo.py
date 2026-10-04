"""Run a repository analysis from the terminal without configuring a web client."""

import argparse
import json
from pathlib import Path

from repopilot.agent import InvestigationResult, Investigator
from repopilot.config import Settings
from repopilot.domain import AnalysisResult
from repopilot.local_model import LocalChatModel
from repopilot.service import RepoPilotService


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    parser.add_argument("--issue", required=True, help="Issue description, not a file path")
    parser.add_argument("--local-model", help="Local server model alias, e.g. qwen3-4b")
    parser.add_argument("--model-url", default="http://127.0.0.1:8081/v1")
    parser.add_argument("--output", type=Path, help="Optionally save the JSON result")
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    service = RepoPilotService(Settings(allowed_root=repository.parent))
    summary = service.index(repository)
    result: AnalysisResult | InvestigationResult
    if args.local_model:
        result = Investigator(
            service,
            model_factory=lambda: LocalChatModel(args.local_model, args.model_url),
        ).investigate(args.issue)
    else:
        result = service.analyze(args.issue, 5, "bm25")
    output = json.dumps(
        {"index": summary.model_dump(), "result": result.model_dump()},
        ensure_ascii=False,
        indent=2,
    )
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
