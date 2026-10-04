"""Check citation provenance against source lines actually returned by read_file.

This validates observation and line ranges, never causal correctness.
"""

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from repopilot.service import RepoPilotService


class Citation(BaseModel):
    file_path: str = Field(min_length=1, max_length=1000)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)


class CheckedCitation(Citation):
    verified: bool
    problems: list[str] = Field(default_factory=list)
    content: str = ""


class EvidenceAssessment(BaseModel):
    status: Literal["verified", "insufficient"]
    checks: list[str]
    citations: list[CheckedCitation]
    successful_reads: int


def assess_evidence(
    service: RepoPilotService,
    citations: list[Citation],
    evidence_files: list[str],
    trace: list[Any],
) -> EvidenceAssessment:
    observed: dict[str, set[int]] = {}
    reads = 0
    for tool in trace:
        if tool.name != "read_file":
            continue
        try:
            result = json.loads(tool.output)
            if not isinstance(result, dict) or "error" in result:
                continue
            path = result["file_path"]
            source = service.read_file(path).splitlines()
            seen = observed.setdefault(path, set())
            matched = 0
            for line in result["content"].splitlines():
                match = re.fullmatch(r"(\d+): (.*)", line)
                if match:
                    number = int(match[1])
                    if 1 <= number <= len(source) and source[number - 1] == match[2]:
                        seen.add(number)
                        matched += 1
            reads += bool(matched)
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
    checks: list[str] = []
    checked: list[CheckedCitation] = []
    if not reads:
        checks.append("no_source_read")
    if not citations:
        checks.append("missing_citations")
    for citation in citations:
        problems: list[str] = []
        content = ""
        if citation.file_path not in evidence_files:
            problems.append("citation_file_not_listed")
        try:
            lines = service.read_file(citation.file_path).splitlines()
        except ValueError:
            lines = []
        if citation.end_line < citation.start_line or citation.end_line > len(lines):
            problems.append("invalid_line_range")
        elif citation.end_line - citation.start_line >= 200:
            problems.append("citation_range_too_large")
        elif not set(range(citation.start_line, citation.end_line + 1)).issubset(
            observed.get(citation.file_path, set())
        ):
            problems.append("citation_not_read")
        else:
            content = "\n".join(lines[citation.start_line - 1 : citation.end_line])
        checks.extend(problems)
        checked.append(
            CheckedCitation(
                **citation.model_dump(),
                verified=not problems,
                problems=problems,
                content=content,
            )
        )
    grounded_files = {item.file_path for item in checked if item.verified}
    if set(evidence_files) - grounded_files:
        checks.append("uncited_evidence_file")
    implementation = {
        path
        for path in grounded_files
        if path.endswith(".py")
        and not any(
            part in {"test", "tests"} or part.startswith("test_") or part.endswith("_test.py")
            for part in path.split("/")
        )
    }
    if not implementation:
        checks.append("no_implementation_citation")
    return EvidenceAssessment(
        status="insufficient" if checks else "verified",
        checks=list(dict.fromkeys(checks)),
        citations=checked,
        successful_reads=reads,
    )
