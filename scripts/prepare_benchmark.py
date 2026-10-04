"""Prepare pinned public Git checkouts without installing or executing target code."""

import argparse
import json
import re
import subprocess
from pathlib import Path


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "--dataset", type=Path, default=Path("evaluation/investigation_cases.jsonl")
    )
    args = parser.parse_args()
    cases = [json.loads(line) for line in args.dataset.read_text().splitlines() if line.strip()]
    root = args.destination.resolve()
    root.mkdir(parents=True, exist_ok=True)
    mapping = {}
    for case in cases:
        name, revision = case["repository"], case["revision"]
        if not re.fullmatch(r"[A-Za-z0-9][\w.-]*/[A-Za-z0-9][\w.-]*", name) or not re.fullmatch(
            r"[0-9a-f]{40}", revision
        ):
            raise ValueError("Expected GitHub owner/repo and a full commit SHA")
        slug = name.replace("/", "--")
        clone = root / "cache" / slug
        expected_url = f"https://github.com/{name}.git"
        if not clone.exists():
            clone.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--quiet",
                    "--filter=blob:none",
                    "--no-checkout",
                    expected_url,
                    str(clone),
                ],
                check=True,
            )
        elif git("-C", str(clone), "remote", "get-url", "origin") != expected_url:
            raise ValueError(f"Unexpected remote in {clone}")
        checkout = root / "snapshots" / f"{slug}-{revision[:12]}"
        if not checkout.exists():
            checkout.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(clone),
                    "worktree",
                    "add",
                    "--quiet",
                    "--detach",
                    str(checkout),
                    revision,
                ],
                check=True,
            )
        if git("-C", str(checkout), "rev-parse", "HEAD") != revision:
            raise ValueError(f"Wrong revision in existing {checkout}")
        if git("-C", str(checkout), "status", "--porcelain"):
            raise ValueError(f"Dirty checkout: {checkout}")
        mapping[f"{name}@{revision}"] = str(checkout)
    destination = root / "checkouts.json"
    destination.write_text(json.dumps(mapping, indent=2) + "\n")
    print(destination)


if __name__ == "__main__":
    main()
