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
