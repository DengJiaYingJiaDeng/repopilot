# RepoPilot

RepoPilot is an experimental local repository retrieval and issue-investigation system designed to evolve into an Agentic RAG coding assistant.

## Problem

An issue report often names a symptom, while the relevant code is spread across files and symbols. RepoPilot v0.1 turns a local repository into searchable code chunks and returns likely investigation starting points. It does **not** infer a root cause or generate a fix.

## Current features

- Scan `.py` and `.md` files under a configured local root; ignore build and dependency directories, binary files, oversized files, and symlinks.
- Extract Python modules, classes, functions, and async functions with AST and line ranges; split Markdown by headings.
- Rank chunks with a simple, explainable keyword score over paths, symbol names, and content.
- Expose health, indexing, search, and basic issue-context analysis through FastAPI.
- Keep one repository index in process memory. Indexing another repository replaces it; restarting the process clears it.

## Architecture

```text
local repository
  -> ingestion.py: safe file scan
  -> parsing.py: Python AST / Markdown sections
  -> CodeChunk objects
  -> service.py: in-memory index
  -> retrieval.py: keyword ranking
  -> api/app.py: HTTP responses
```

`CodeChunk` records path, symbol, language, content, and line range so later retrieval methods can use the same source representation. `Retriever` has one method because keyword search is currently its only implementation. Vector, hybrid, evaluation, and agent modules will be introduced when their behavior is implemented, rather than as empty classes.

## Quick start

Requires Python 3.12 or newer.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
export REPOPILOT_ALLOWED_ROOT=/absolute/path/to/your/workspace
uvicorn repopilot.api.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs` for interactive API documentation. Set `REPOPILOT_ALLOWED_ROOT` to the parent directory of repositories you want to index. By default it is the server's current working directory. The API rejects paths outside that root and skips symlinks inside a repository.

Example:

```bash
curl -X POST http://127.0.0.1:8000/repositories/index \
  -H 'Content-Type: application/json' \
  -d '{"path":"/absolute/path/to/your/workspace/project"}'

curl -X POST http://127.0.0.1:8000/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"environment config","top_k":5}'

curl -X POST http://127.0.0.1:8000/analyze \
  -H 'Content-Type: application/json' \
  -d '{"issue_text":"MCP server configuration fails to load","top_k":5}'
```

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Readiness response, `{"status":"ok"}` |
| `POST /repositories/index` | Replace the in-memory index from a local path; report indexed and skipped files |
| `POST /search` | Return up to `top_k` scored code chunks |
| `POST /analyze` | Return retrieved chunks plus deduplicated files and symbols for an issue description |

Search before indexing returns HTTP 409. Invalid or disallowed repository paths return HTTP 400. `/analyze` only retrieves likely context; it does not provide a root-cause hypothesis, investigation plan, or test plan yet.

## Testing

```bash
ruff check .
ruff format --check .
mypy
pytest
```

The tests cover file filtering, symlink and path boundaries, AST symbols and line numbers, keyword ranking, and the API flow. They use a small repository in `tests/fixtures/sample_repo` and need no model API key.

## Docker

```bash
docker build -t repopilot:0.1 .
docker run --rm -p 127.0.0.1:8000:8000 \
  -v /absolute/path/to/your/workspace:/workspace:ro \
  -e REPOPILOT_ALLOWED_ROOT=/workspace repopilot:0.1
```

If PyPI is slow in your region, pass `--build-arg PIP_INDEX_URL=<your trusted package index>` to `docker build`. Use `/workspace/project` as the indexing path from inside the container. The server has no authentication, so keep it bound to localhost. It reads local source contents and returns matched contents through the API; avoid indexing confidential repositories unless that behavior is acceptable in your environment.

## Roadmap

- **v0.1 (current):** repository ingestion, AST parsing, keyword retrieval, FastAPI, tests and CI.
- **v0.2:** implement BM25, then embeddings and hybrid retrieval; compare against the v0.1 baseline.
- **v0.3:** add reranking and a labeled issue-to-file retrieval evaluation set.
- **v0.4:** add a small bounded agent loop for investigation steps.
- **v0.5:** explore LangGraph when workflow state and human review require it.
- **v0.6:** expose selected search tools through MCP.
- **v1.0:** a measured, documented repository analysis system, contingent on evaluation results.

For current baseline observations and the next milestone checklist, see [Development log](docs/DEVELOPMENT_LOG.md).

## Project status

This is a learning and portfolio project. Keyword scores indicate textual overlap, not correctness. Python syntax errors are reported as skipped files. The current index is ephemeral and scoped to one repository per server process. No LLM, embedding, BM25, reranker, database, frontend, or autonomous agent has been implemented.
