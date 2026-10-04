# RepoPilot

RepoPilot is an experimental repository retrieval and issue investigation system. It indexes a local Python repository, ranks likely files and symbols for a bug report, and can optionally ask an LLM to form a **tentative** root-cause hypothesis with investigation steps and a test plan.

## Why it exists

Issue reports describe symptoms; the related code can be spread across modules, tests, and symbols. RepoPilot makes the retrieval step measurable and provides bounded, read-only tools for further investigation. It never edits the target repository or claims to have executed its tests.

## Implemented

- Safe local ingestion of `.py` and `.md` files under `REPOPILOT_ALLOWED_ROOT`; ignores dependencies, symlinks, binary and oversized files.
- AST extraction of Python modules, classes, functions, and async functions with source line ranges; Markdown section splitting.
- Keyword and BM25 retrieval; optional embedding cosine search, BM25/vector reciprocal-rank fusion, and cross-encoder reranking.
- File-level Recall@K and MRR@K evaluation from JSONL labels, including a five-issue [Click benchmark](evaluation/README.md) at a pinned pre-fix revision.
- FastAPI endpoints for indexing, search, context analysis, and bounded LLM investigation through a local model or optional OpenAI provider.
- A read-only four-tool MCP server; an optional LangGraph workflow that routes incomplete or insufficiently grounded investigations to review.
- Ruff, strict mypy, pytest, GitHub Actions, and a default Docker image that requires no model key.

## Architecture

```text
repository -> safe scan -> Python AST / Markdown chunks -> in-memory snapshot
                                                |
issue text -> keyword / BM25 / optional vector + hybrid + reranker
                                                |
                  /search, /analyze, evaluation, MCP tools
                                                |
             optional model tool loop -> /investigate
                            optional LangGraph routing
```

`CodeChunk` keeps repository-relative path, symbol, source, and line range. Retriever implementations share `index` and `search`. The model can only call `search_code`, `read_file`, `find_symbol`, and `find_callers` against the indexed snapshot. The loop caps tool calls and rejects cited files absent from observed evidence. A hypothesis remains unverified until a developer checks the code and runs tests.

## V2: source evidence and paired evaluation

V0.9 adds Python caller candidates, line-by-line citation provenance checks, explicit uncertainty/review states, and a bounded structured synthesis step for the local model. Ten pinned Click/Requests cases compare the original and updated investigation pipeline. See the [V2 results and limitations](evaluation/V2_REPORT.md). Citation verification is **not** root-cause verification.

## Visual workbench (v0.9)

An independent React/TypeScript frontend turns investigation JSON into four views: **summary, code evidence, tool-call timeline, and proposed tests**. It supports local JSON import/export and live investigations through FastAPI. New investigations can request Chinese prose; historical/imported output is kept unchanged.

After the Python, local-model, and frontend dependencies are installed:

```bash
bash scripts/start_workbench.sh
```

Open **http://127.0.0.1:5173**. The page starts with a clearly labeled historical fixture report. Import your own `result.json` or choose a local repository and start a new investigation. See the [full frontend/backend setup and reading guide](docs/WEB_WORKBENCH.md).

## Quick start

Requires Python 3.12+.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
export REPOPILOT_ALLOWED_ROOT=/absolute/path/to/workspace
uvicorn repopilot.api.app:app --host 127.0.0.1 --port 8000
```

Interactive API documentation is at `http://127.0.0.1:8000/docs`. Index a repository beneath the allowed root:

```bash
curl -X POST http://127.0.0.1:8000/repositories/index \
  -H 'Content-Type: application/json' \
  -d '{"path":"/absolute/path/to/workspace/project"}'
curl -X POST http://127.0.0.1:8000/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"environment config","top_k":5,"method":"bm25"}'
curl -X POST http://127.0.0.1:8000/analyze \
  -H 'Content-Type: application/json' \
  -d '{"issue_text":"MCP server configuration fails to load","method":"bm25"}'
```

| Endpoint | Behavior |
| --- | --- |
| `GET /health` | Readiness response |
| `GET /workspace` | Available retrieval methods, configured model, allowed root, and example path |
| `POST /repositories/index` | Replace the single in-memory repository snapshot |
| `POST /search` | Return scored chunks and source excerpts |
| `POST /analyze` | Return retrieved files and symbols; no generated hypothesis |
| `POST /investigate` | Optional model tool loop; returns hypothesis, steps, plan, evidence, and tool trace |

Use `method=keyword` or `bm25` by default. `vector` and `hybrid` require an embedding provider; `rerank` requires a configured cross-encoder. Search before indexing returns HTTP 409. An unavailable method returns HTTP 400. Investigation without an LLM configuration returns HTTP 503.

## Optional model features

### Local embeddings and reranking

```bash
python -m pip install -e ".[local]"
export REPOPILOT_EMBEDDING_PROVIDER=local
export REPOPILOT_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
export REPOPILOT_RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L6-v2
```

The first run downloads model weights. Set `REPOPILOT_EMBEDDING_PROVIDER=none` and omit `REPOPILOT_RERANK_MODEL` for the lightweight default. See the [local setup guide](docs/LOCAL_MODELS.md) for the tested CPU dependency constraints and pinned model snapshots. All five retrieval methods have been run with real weights; results are below.

### Local investigation without an API key

A local Qwen3-4B GGUF model runs through llama.cpp. Follow the [download and startup guide](docs/LOCAL_MODELS.md), then:

```bash
bash scripts/start_local_model.sh  # terminal A
# terminal B, with .venv activated:
python -m repopilot.demo tests/fixtures/sample_repo \
  --issue 'MCP_SERVER_NAME is empty but server startup accepts it. Investigate the validation path.' \
  --local-model qwen3-4b --output /tmp/repopilot-demo.json
```

For the API, configure `REPOPILOT_INVESTIGATION_PROVIDER=local` and `REPOPILOT_INVESTIGATION_MODEL=qwen3-4b`. Each investigation has its own chat session. The first turn requires a source read; subsequent turns can search, read other line ranges, find symbols, or conclude. The tool budget, JSON schema, and observed-file checks remain active. `complete` means protocol completion, not a verified root cause. See the [live model report](evaluation/LOCAL_MODEL_REPORT.md) for actual outputs and failure analysis.

### OpenAI embeddings and investigation

```bash
python -m pip install -e ".[openai]"
export REPOPILOT_OPENAI_API_KEY=your_key_here
export REPOPILOT_EMBEDDING_PROVIDER=openai
export REPOPILOT_EMBEDDING_MODEL=text-embedding-3-small
export REPOPILOT_INVESTIGATION_MODEL=your_responses_api_model
# Optional explicit graph: python -m pip install -e ".[graph]"
# export REPOPILOT_INVESTIGATION_WORKFLOW=langgraph
```

Then index a repository and call `/investigate` with `{"issue_text":"...","method":"hybrid"}`. OpenAI embedding at indexing time sends chunk text to the API and incurs API usage. Investigation sends issue text, retrieved source excerpts, and tool results to the API. Use only repositories you are authorized to send to that provider. No API key belongs in a commit. The live OpenAI path needs a valid key and was not exercised by the offline test suite.

## MCP

```bash
python -m pip install -e ".[mcp]"
python -m repopilot.mcp_server /absolute/path/to/workspace/project
```

This starts a local stdio MCP server with `search_code`, `read_file`, `find_symbol`, and `find_callers`. It indexes one repository on launch. Standard output is reserved for MCP protocol messages. The tools read only the snapshot; they do not execute shell commands or modify files.

## Evaluation

```bash
python -m repopilot.evaluation /path/to/click-at-8.2.1 \
  evaluation/click_8_2_1_issues.jsonl --top-k 3
```

On Click commit `fd183b2ced1cb5857784fe7fb22f4982f671f098`, with five manually selected historical issues and source-file labels:

| Method | File Recall@3 | File MRR@3 |
| --- | ---: | ---: |
| Keyword | 0.40 | 0.367 |
| BM25 | 0.90 | 0.80 |
| MiniLM vector | 0.80 | 0.50 |
| BM25 + vector RRF | 0.80 | 0.767 |
| Hybrid + cross-encoder | 0.80 | 0.90 |

The cross-encoder improved first-hit ranking on this set, while BM25 retained the highest recall. More model components did not consistently improve retrieval. [Per-case outputs and model versions](evaluation/results/) are committed. BM25 missed one of two relevant source files for issue #2952 in the top three and ranked tests before source for some cases. This small **development** set was selected and checked manually; the scores do not establish generalization. The included synthetic fixture exists only to test the evaluator. Use a larger held-out set before making broad quality claims.

## Verification

```bash
ruff check .
ruff format --check .
mypy
pytest
```

Offline tests use fake embedding and model providers where needed. Live Qwen and MiniLM runs are recorded separately and are not required by CI. The MCP tools are also tested with the official SDK's in-memory client. CI runs the same checks on pushes and pull requests.

## Docker

```bash
docker build -t repopilot:0.9 .
docker run --rm -p 127.0.0.1:8000:8000 \
  -v /absolute/path/to/workspace:/workspace:ro \
  -e REPOPILOT_ALLOWED_ROOT=/workspace repopilot:0.9
```

Use `/workspace/project` for the index request in the container. If PyPI is slow, pass `--build-arg PIP_INDEX_URL=<trusted-index>` during build. The default image includes lexical retrieval and the API; install optional extras in a custom image for model or MCP features. The server has no authentication and should stay bound to localhost.

## Scope and limitations

This is a portfolio-grade **prototype**, not a production coding agent. The index holds one repository per process and disappears on restart. Python module chunks duplicate symbol text, which can bias ranking. Chinese issue text is not segmented by the lexical tokenizer. There is no database, authorization layer, autonomous code modification, or cloud deployment. Local embedding, reranking, and LLM paths have been exercised with downloaded models. OpenAI adapters have only been checked with fake providers. The development dataset is too small to establish diagnosis accuracy. Do not reindex while an investigation is in progress; concurrent snapshot replacement is not supported. See the [development log](docs/DEVELOPMENT_LOG.md) for decisions and measured observations.
