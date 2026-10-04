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
