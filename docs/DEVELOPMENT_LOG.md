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

## 2026-10-05 — owner handoff checklist

These are the steps for the project owner to do personally before claiming technical ownership in a resume or interview:

- [ ] Clone the GitHub repository into a fresh directory. Follow the README to install and run it without using the existing local `.venv`.
- [ ] Trace one request from `POST /repositories/index` through file scanning, AST parsing, `CodeChunk`, and `Retriever.index`; explain each step in your own words.
- [ ] Trace one `/search` request and calculate one chunk's keyword score by hand. Explain why a test or module chunk may rank ahead of a function.
- [ ] Run the three queries above on your clone. Record any changed rankings and why they changed.
- [ ] Find 3–5 real, closed GitHub issues with linked fixes from one public Python repository. Record the issue text and changed file paths in personal notes using `{"issue_id": "...", "issue_text": "...", "relevant_files": ["..."]}`; do not add a full evaluation dataset or metric code yet.
- [ ] Create a branch named `feat/bm25-retrieval` when ready to implement the next milestone yourself. Open a pull request to this repository's `main` after local checks pass.

### Next milestone: BM25 retrieval

Implement BM25 yourself using the existing `Retriever` contract. First decide how to tokenize queries and chunks and which fields receive weight. During `index`, calculate document frequency and document length statistics. During `search`, return scored chunks with deterministic tie ordering. Preserve the existing API responses.

Acceptance checks for that PR:

- [ ] A clear explanation of the scoring formula and any field weighting appears in the PR description.
- [ ] Unit tests cover an exact match, a term occurring in multiple chunks, a length-sensitive case, an empty query, and reindexing a different repository.
- [ ] Ruff, mypy, pytest, and CI pass without an external model API.
- [ ] Compare the keyword baseline and BM25 on the same hand-checked issue examples; report successes and failures, not only favorable cases.

### Resume evidence to build over the next 1–2 months

A credible project entry needs a runnable demo, a documented test set, measured retrieval quality, a clear explanation of your own changes, and honest failure analysis. Your own repository's pull requests show your development process; an accepted contribution to another project's repository is a separate open-source contribution.

Current wording may say **local repository retrieval and issue-context analysis baseline**. Do not describe v0.1 as a finished Agent, RAG generator, root-cause analyzer, or production deployment.
