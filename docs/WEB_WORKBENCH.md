# Visual investigation workbench

RepoPilot v0.9 includes an independent **React + TypeScript + Vite** frontend in `frontend/`. FastAPI remains the backend in `src/repopilot/api/`. They run as separate processes and communicate through HTTP; the browser never directly calls the model server.

```text
Browser / React :5173
    ├─ GET /workspace                     runtime capabilities
    ├─ POST /repositories/index           repository snapshot
    └─ POST /investigate                  response_language=zh
                  ↓
       FastAPI :8000 → LangGraph → local Qwen :18081
```

The default UI is Chinese. An included historical report from the public synthetic fixture provides a first look. It is clearly labeled as a historical example, with a separate manual explanation. New investigations request Chinese prose while preserving JSON keys and code identifiers. If the local model still answers in English, one additional tool-free model call produces a Chinese rendering. The original answer is retained in `original_output_text`, with an explicit `translation_note` in the UI. Translation only returns a flat array of prose strings; the application retains paths, line numbers, and array lengths unchanged; invalid translation falls back to the original. This improves readability, not diagnosis accuracy. Imported reports preserve their original language and text.

## Start everything locally

First follow the Python setup in the main README and the model download steps in [LOCAL_MODELS.md](LOCAL_MODELS.md). For the frontend, use Node.js 24 and pnpm 11.19.0:

```bash
corepack prepare pnpm@11.19.0 --activate
pnpm --dir frontend install --frozen-lockfile
bash scripts/start_workbench.sh
```

If your Node distribution does not include Corepack, install pnpm through its official installation instructions. The script builds the frontend, starts three loopback services, waits for readiness, and prints **http://127.0.0.1:5173**. Keep the terminal open; Ctrl+C stops only the child processes started by this script. Port conflicts produce an error rather than stopping an existing service. Logs are under `.local/workbench/`, ignored by Git.

`FRONTEND_PORT`, `BACKEND_PORT`, `MODEL_PORT`, `REPOPILOT_PYTHON`, and `REPOPILOT_ALLOWED_ROOT` can override defaults. The allowed root defaults to the parent of the RepoPilot repository. A custom root must include any repository you want to index.

## Separate development servers

```bash
# Terminal A: model (see the model guide)
MODEL_PORT=18081 bash scripts/start_local_model.sh

# Terminal B: backend, virtual environment activated
REPOPILOT_ALLOWED_ROOT=/absolute/path/to/workspace \
REPOPILOT_INVESTIGATION_PROVIDER=local \
REPOPILOT_INVESTIGATION_MODEL=qwen3-4b \
REPOPILOT_LOCAL_MODEL_URL=http://127.0.0.1:18081/v1 \
REPOPILOT_INVESTIGATION_WORKFLOW=langgraph \
uvicorn repopilot.api.app:app --host 127.0.0.1 --port 8000

# Terminal C: frontend
pnpm --dir frontend dev
```

The frontend defaults to `http://127.0.0.1:8000`; `VITE_API_BASE_URL` overrides that address at development/build time. FastAPI's default CORS list permits only localhost/127.0.0.1 on port 5173. For different origins, set `REPOPILOT_CORS_ORIGINS` as a JSON list. The [FastAPI CORS documentation](https://fastapi.tiangolo.com/tutorial/cors/) explains how origins include ports. See the [Vite guide](https://vite.dev/guide/) for frontend environment setup.

## Read a report

| View | Meaning |
| --- | --- |
| 调查摘要 | Model hypothesis, cited files, suggested investigation steps. Completed means the protocol finished, not that the diagnosis is correct. |
| 代码证据 | Initial retrieval and successful tool-read snippets, grouped by file with source line numbers. Scores are relevance scores, not confidence percentages. |
| 调用轨迹 | Actual tool calls in order, including arguments, failures, and retries. These are displayed after the request finishes; the current API does not stream tool events. |
| 验证计划 | Model-proposed tests. The app does not execute or mark them as passed. |

The manual explanation on the example is specific to the fixture and does not replace the model's original output. The current fixture's validation helper returns a boolean which the startup method ignores; the displayed model output does not fully establish that causal path.

## Import and export

Click **导入报告** and select the CLI's `result.json` or a raw `/investigate` JSON response. The browser validates the shape and size (up to 5 MB), then renders the report **locally**. Imported files are not sent to the backend. No results are automatically stored in localStorage. **导出 JSON 报告** opens a save dialog with a JSON download and a copyable full report. If the browser does not start a download, use **复制完整报告** or copy the read-only text into a `.json` file; refresh clears the current view and restores the example.

When the backend is unavailable, example/import/export still work. New investigation is disabled until the backend is connected and a model is configured. A configured model is not guaranteed to be healthy; provider failures are shown as incomplete investigations with the retained trace.

## Verification

```bash
pnpm --dir frontend test
pnpm --dir frontend build
pytest
ruff check .
mypy
```

Frontend tests cover report validation, raw API/CLI envelopes, rejection of malformed input, successful evidence extraction, and preservation of tool errors. The project CI separately checks Python and the frontend build/tests. Browser acceptance additionally covers actual import, tab navigation, copying the complete export, and the real local-model request path including Chinese rendering. The in-app browser did not emit a download event during acceptance, so file download is not claimed as verified; the copy export provides a tested alternative.

## Scope

This is a local, single-user workbench. The backend still holds one repository snapshot per process; do not reindex from another tab during an investigation. No authentication, persistent task queue, streaming model output, automated repair, or cloud deployment is included. The Python Docker image remains backend-only; `frontend/` can be built independently, and the documented three-process host setup is the tested local route.

## V2 evidence review

New reports show **证据检查**, concrete file/line citations, and **尚待确认**. A verified range means every quoted line was actually returned by a successful `read_file` call and matches the indexed snapshot. It does not verify the explanation. Missing citations, unread/truncated lines, files without valid citations, and test-only evidence require review. Old reports remain importable and are labeled unchecked; importing a saved report does not re-run the backend checks.

The local model gets one tool-free, JSON-schema-constrained synthesis call using actual source reads. The unverified draft is retained separately and is not passed into synthesis, to reduce anchoring on an earlier mistake. At the tool budget, the local adapter attempts this bounded final report without requesting more tools. If synthesis fails, the existing validation still applies. This adds latency; results and failures are in [the V2 evaluation](../evaluation/V2_REPORT.md).

**查找候选调用方** uses Python AST name matching. It ignores comments and string literals, but does not resolve imports, aliases, receiver types, inheritance, or dynamic dispatch. The UI labels matches as candidates. The model must read the relevant source before relying on the relationship.
