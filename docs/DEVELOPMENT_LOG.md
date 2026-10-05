# Development log

## 2026-10-04 — v0.1 baseline

RepoPilot v0.1 reads local Python and Markdown files, extracts code symbols and sections, and ranks chunks by keyword overlap. It does not call a language model or diagnose a root cause.

### Architecture decisions

- `CodeChunk` is the shared retrieval unit: it preserves source path, symbol, content, and line range.
- `Retriever.index(chunks)` and `Retriever.search(query, top_k)` separate corpus preparation from querying. A future BM25 implementation can calculate corpus statistics during `index` without changing the API layer.
- The HTTP server only indexes paths under `REPOPILOT_ALLOWED_ROOT`. The default is the server's current directory. Symlinks, oversized files, binary files, and unreadable UTF-8 files are skipped.
- The index holds one repository per process. A second indexing request replaces the first index.
- No Vector/Hybrid/Agent placeholder classes are present. They should be added when their real behavior and tests exist.

### Manual smoke check

Indexing this repository produced **20 files** and **78 chunks** at the time of this check. These are smoke-check counts, not retrieval-quality metrics. Example top results:

| Query | Top result | Observation |
| --- | --- | --- |
| `ignore symlink binary oversized file` | `src/repopilot/ingestion.py`, `SourceFile` | The name's `File` token can outweigh a more useful implementation chunk. |
| `Python AST async function line numbers` | `tests/test_parsing.py`, parser test | Test code can rank above `parse_python`. |
| `keyword retrieval scoring` | `src/repopilot/retrieval.py`, module chunk | A whole-file chunk can rank above a specific symbol. |

The current tokenizer uses English letters and digits, with underscore and camel-case splitting. It does not segment Chinese issue text. Keyword overlap ignores term frequency and document length. These weaknesses are reasons to compare against BM25 later; do not claim that BM25 will automatically solve every ranking error.

### Verified gates

- Python 3.12: Ruff lint and format, mypy, and pytest pass.
- Docker image builds with a configurable package index. A live container returned `{"status":"ok"}`, indexed the read-only fixture (5 files, 12 chunks), and ranked `load_environment_config` first for `environment config`.
- GitHub Actions CI passes on `main`.

## 2026-10-04 — v0.2 retrieval evaluation

- Added BM25 with path terms repeated twice and symbol terms three times. This is an explicit field weighting heuristic, not a tuned model.
- Added file-level Recall@K and MRR@K evaluation from checked JSONL labels. Deduplicating paths prevents multiple chunks from one file consuming the file-level ranking.
- On the two synthetic smoke cases, keyword scores Recall@3 = 1.0 and MRR@3 = 1.0; BM25 scores Recall@3 = 1.0 and MRR@3 = 0.5. The tiny synthetic fixture verifies plumbing only. It provides no evidence that either method generalizes to real issues.
- Next: create a real issue dataset at a pinned repository revision, then compare semantic and hybrid methods against these baselines.

## 2026-10-04 — v0.6 portfolio prototype

### Retrieval

- Added optional cosine retrieval over embeddings and BM25/vector reciprocal-rank fusion. The embedding interface accepts fake providers for deterministic offline tests; the optional OpenAI and SentenceTransformer adapters load only when configured.
- Added optional cross-encoder reranking of at most a configured candidate pool. No model weights or API calls are required for the default path.
- Pinned a five-issue Click development benchmark at pre-fix commit `fd183b2ced1cb5857784fe7fb22f4982f671f098`. The labels come from source files changed in linked fixes; see `evaluation/README.md` for provenance. Keyword scored Recall@3 0.40 / MRR@3 0.367; BM25 scored Recall@3 0.90 / MRR@3 0.80. The set is too small and selected to support broad quality claims.
- Failure analysis: BM25 retrieves only `src/click/core.py` of two labeled files for issue #2952 in the top three. For #2836 it ranks a test file first; for #2952 it ranks a test file first. Exact issue wording and test files can dominate path or symbol evidence.

### Investigation and tool integration

- The optional model loop uses the OpenAI Responses function-calling pattern. It only dispatches read-only indexed tools, caps total tool calls, validates arguments, records outputs, and rejects final citations that did not appear in observed evidence. A model hypothesis is never a verified diagnosis.
- LangGraph is an optional alternate workflow with explicit retrieval, investigation, and review routing. Incomplete model output sets `review_required` in the API response.
- The MCP v2 stdio server exposes `search_code`, `read_file`, and `find_symbol` for a single explicitly selected repository. An in-memory SDK client test calls all three tools.

### Limits and next evidence

- The default Docker build and lexical evaluation are runnable without a key. The model-backed retrieval, reranker, and live LLM response have not been evaluated against a real downloaded model or API key in this environment; fake-provider tests verify wiring, not model quality.
- The benchmark is a development set. A held-out issue set and an error audit would be needed for stronger retrieval claims.
- The index remains in memory and one-repository-only. The server has no authentication, so it is intentionally local-only.

## 2026-10-04 — v0.7 live local model validation

- Added a loopback Chat Completions adapter for Qwen/llama.cpp, with a fresh session per investigation, required initial source read, disabled internet proxies, refused redirects, output size/token checks, and explicit provider-error results.
- Added source line ranges and truncation metadata to the model's read tool. All incomplete direct investigations now set the review flag, matching graph routing.
- Ran actual MiniLM embedding/reranking: BM25 Recall@3 0.90 / MRR@3 0.80; hybrid 0.80 / 0.767; reranked hybrid 0.80 / 0.90. All five methods and pinned model versions are recorded under `evaluation/results/`.
- Ran all five Click investigations through FastAPI + LangGraph + local Qwen3-4B. After resolving tool-choice compatibility and context/prompt failures, all five completed the protocol with 2–3 real tool calls. This did **not** establish diagnosis accuracy: manual inspection found wrong and weak hypotheses, documented in `evaluation/LOCAL_MODEL_REPORT.md`.
- Added a terminal demo, local server startup script, and CPU dependency constraints. Runtime binaries and model weights are stored outside the Git repository. OpenAI's live path remains untested without credentials.
- This supersedes the earlier v0.6 note that downloaded-model paths were untested. The current deliverable is a runnable portfolio prototype with measured limitations.

### v0.7 delivery checks

- 46 offline tests passed; Ruff lint/format and strict mypy passed.
- The terminal demo ran against a real local model, including recovery from an invalid line range, and returned a structured hypothesis. Its server process was stopped afterward.
- Docker `repopilot:0.7` built and passed a live HTTP smoke check with a read-only fixture mount: health, indexing, BM25 search, version metadata, and HTTP 503 for an unconfigured investigation model. The test container was removed.

## 2026-10-04 — v0.8 visual workbench

- Added an independent React/TypeScript/Vite frontend with Chinese navigation, a clearly labeled historical fixture example, validated local JSON import/export, and live FastAPI investigation requests.
- The report has separate summary, source evidence, actual tool timeline, and proposed-test views. Failed tool calls are retained. A completed protocol is explicitly distinguished from a correct diagnosis or an executed test.
- Added `/workspace` capability metadata and a restricted loopback CORS allowlist. The page offers only retrieval methods actually configured in the backend.
- Added request-scoped language preference through FastAPI and LangGraph. The local model sometimes continued in English despite Chinese instructions, so an optional, single translation call now preserves the original answer and checks unchanged evidence paths and list lengths. Both the translation notice and original are visible. This does not fix erroneous hypotheses.
- Added `scripts/start_workbench.sh` to build and start the frontend, backend, and local model as separate processes; it waits for readiness, refuses occupied ports, and stops only its children on exit. Private machine-specific wrappers and Chinese study notes remain outside Git.
- Browser acceptance checked actual report import, source line display, tool failure/retry details, test-plan labeling, and a real local-model request. No browser console errors were observed during those flows.

- Final v0.8 acceptance: 51 Python tests and 6 frontend tests pass; Ruff, mypy, TypeScript and production build pass. A real browser request returned a labeled Chinese rendering in 5.8 seconds. JSON file download could not be confirmed in the in-app browser; the export dialog also supports copying the complete report.

## v0.9 — Evidence provenance and paired investigations (2026-10-05)

- Added AST-based `find_callers` candidates to Agent and MCP, with explicit limitations for aliases and dynamic dispatch.
- Added actual-read line citation checks, structured uncertainty, and review routing for insufficient evidence. Old reports remain compatible and unchecked.
- Added one bounded, tool-free local-model synthesis with JSON schema and observed-file constraints; retained the draft separately. Tool-budget exhaustion can finish from existing reads without more tools.
- Expanded evaluation to 10 pinned pre-fix cases across Click and Requests, preserving baseline, failed intermediate runs, a rejected reasoning probe, paired metrics, and qualitative source review.
- Protocol completion 10/10 in both final runs; 22/22 V2 citations passed provenance. Cited-file Recall@3 fell from 0.85 to 0.70; median latency increased from 7.11s to 12.97s. No diagnosis-accuracy improvement is claimed. See `evaluation/V2_REPORT.md`.
- Frontend displays evidence checks, specific line citations, uncertainty, and draft/synthesis distinction.
- Fixed workbench restart preflight falsely reporting TIME_WAIT ports as occupied; actual listening services still prevent startup.
- Local verification: 70 Python tests, 7 frontend tests, Ruff/mypy and production build. The checkout preparation script was exercised against cached repositories without executing upstream code.
- Chinese rendering now translates prose arrays only; paths and line numbers are retained by application code, with dedicated tests.

## v0.9 follow-up — Source read boundaries and a rejected gap heuristic (2026-10-05)

- Investigated the V2 cited-file recall drop by separating initial retrieval, successful `read_file` coverage, and final citations. Added a reproducible read-coverage comparator that rejects mismatched datasets and repository revisions.
- Prototyped a bounded automatic read of function implementations named in the draft. Three implementation variants on the same 10 development cases produced cited-file Recall@3 of 0.95, 0.80, and 0.65, with 8/10, 9/10, and 10/10 provenance-complete reports respectively. The heuristic depended on the model naming the right function and was removed from the default path.
- Corrected `read_file` so its returned `end_line` reflects only complete source lines under the 8,000-character output cap. Continuation flags now describe only an incompletely returned requested range; a short read no longer advertises the rest of the file as a continuation.
- The final boundary-only run yielded 10/10 protocol-complete and provenance-complete reports, but cited-file Recall@3 was 0.65 versus V2's 0.70. This is a tool-output correctness fix, not an accuracy improvement. See `evaluation/V2_1_REPORT.md` for the runs and limitations.
- Local verification: 73 Python tests, Ruff, and mypy. The frontend was unchanged; its existing 7 tests and production build remained the prior validated state.

## v0.9 follow-up — AST symbol sites and model-size check (2026-10-05)

- Audited the 0.70 → 0.65 cited-file Recall@3 drop: only Click #2836 changed, missing one of its two labeled files. The 0.05 difference is one case's 0.5 loss divided by ten; one run per variant does not establish a trend.
- Indexed assignment and import locations from the same trusted Python snapshot as functions/classes. `find_symbol` now exposes type, path and line range for constants, type aliases and attribute writes, including `self.` lookups. A candidate write remains distinct from the value selected at runtime.
- On the ten-case development set with local Qwen3-4B, initial file recall stayed 0.75; actual-read and cited-file Recall@3 rose from 0.65 to 0.90. Protocol and citation provenance passed 10/10, median latency changed 14.04s → 14.17s and mean calls 3.5 → 4.0. Root-cause explanations remained wrong in several cases; file recall is not diagnosis accuracy.
- Compared Qwen3-8B Q4_K_M against Qwen3-4B Q4_K_M on identical source digest, case set, pinned target revisions and agent settings. 8B yielded cited-file Recall@3 0.75, mean 1.9 tool calls and median 17.64s, versus 4B's 0.90, 4.0 and 14.17s. The 8B run frequently stopped after one read and missed causal branches. Both results are single runs on the development set; neither supports a general model ranking.
- Kept 4B as the workbench default. The next honest accuracy milestone is an independent issue set with a root-cause rubric and explicit checking of value origins and downstream branches. See `evaluation/V2_2_REPORT.md`.
- Verification: 76 Python tests, Ruff lint/format, strict mypy, 7 frontend tests and a production frontend build passed. Full model traces and weight files remain outside Git.
