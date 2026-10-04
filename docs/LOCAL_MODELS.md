# Run RepoPilot without an API key

The default retrieval/API needs no model. For generated investigations, RepoPilot can use a local [llama.cpp server](https://github.com/ggml-org/llama.cpp/tree/master/tools/server) and [Qwen3-4B-GGUF](https://huggingface.co/Qwen/Qwen3-4B-GGUF). The adapter uses HTTP Chat Completions over loopback, with internet proxies disabled. Each investigation gets a fresh chat history.

## Tested environment

Linux x86-64, Python 3.12, NVIDIA RTX 3080 Ti (12 GB), driver 535.309.01, llama.cpp Vulkan build `b11382` (`11fe02151`), Qwen3-4B Q4_K_M, 16,384-token context, one inference slot, thinking disabled. This is a local development setup; other operating systems need their matching llama.cpp binaries. The server used about 4.3 GB GPU memory during the initial smoke check (including other desktop usage).

Store runtimes and weights **outside** this repository:

```text
workspace/
├── repopilot/
└── repopilot-models/
    ├── llama-runtime/llama-b11382/llama-server
    ├── qwen3-4b/Qwen3-4B-Q4_K_M.gguf
    └── huggingface/
```

## 1. Optional embedding and reranker stack

Activate the Python 3.12 virtual environment from the README. To avoid downloading a CUDA PyTorch stack for the small retrieval models, install CPU torch first:

```bash
python -m pip install --index-url https://download.pytorch.org/whl/cpu 'torch==2.6.0'
python -m pip install -e '.[local]' -c requirements-local.txt
export HF_HOME="$(pwd)/../repopilot-models/huggingface"
export HF_HUB_DISABLE_XET=1
export OMP_NUM_THREADS=4
export MKL_NUM_THREADS=4
```

The tested MiniLM embedding has 384 dimensions. Model snapshots are recorded in `evaluation/results/local_models_manifest.json`. To reproduce those snapshots exactly, pass their downloaded snapshot directory as the embedding/reranker model setting; bare model names resolve the provider's current default revision.

## 2. Download the local LLM and runtime

For the tested **Linux Vulkan** setup:

```bash
mkdir -p ../repopilot-models/llama-runtime
curl -fL --retry 3 \
  https://github.com/ggml-org/llama.cpp/releases/download/b11382/llama-b11382-bin-ubuntu-vulkan-x64.tar.gz \
  -o ../repopilot-models/llama-runtime/llama-vulkan.tar.gz
printf '%s  %s\n' \
  f6e5729ca608b980e3f17b28c6497f71c558913b53fa5b1142a3be8fe27f303a \
  ../repopilot-models/llama-runtime/llama-vulkan.tar.gz | sha256sum --check
# Extract only after the checksum passes.
tar -xzf ../repopilot-models/llama-runtime/llama-vulkan.tar.gz \
  -C ../repopilot-models/llama-runtime
python - <<'PY'
from huggingface_hub import hf_hub_download
hf_hub_download(
    repo_id="Qwen/Qwen3-4B-GGUF",
    revision="bc640142c66e1fdd12af0bd68f40445458f3869b",
    filename="Qwen3-4B-Q4_K_M.gguf",
    local_dir="../repopilot-models/qwen3-4b",
)
PY
printf '%s  %s\n' \
  7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5 \
  ../repopilot-models/qwen3-4b/Qwen3-4B-Q4_K_M.gguf | sha256sum --check
```

Qwen's weight download is about 2.5 GB. Hugging Face Hub comes with the local extra; if you only want the LLM, install `huggingface-hub==0.36.2` instead of the retrieval stack. Check the official [llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases) for the binary matching your platform. `LLAMA_SERVER`, `MODEL_PATH`, `REPOPILOT_MODELS_DIR`, `MODEL_PORT`, `GPU_LAYERS`, and `CONTEXT_SIZE` can override the startup script's defaults.

## 3. Run a terminal demonstration

In terminal A, from the repository root:

```bash
bash scripts/start_local_model.sh
```

Wait for the server to listen on `127.0.0.1:8081`. In terminal B:

```bash
python -m repopilot.demo tests/fixtures/sample_repo \
  --issue 'MCP_SERVER_NAME is an empty string but server startup accepts it. Locate the validation path and propose a regression test.' \
  --local-model qwen3-4b --output /tmp/repopilot-demo.json
```

The fixture is a synthetic smoke case, not a historical issue. Omit `--local-model` to run only BM25 context retrieval. The JSON includes the indexed-file counts, source evidence, tool trace, hypothesis and test plan. No target tests are executed and no fixes are applied.

The local adapter offers `read_file` as a required first call; later calls can use all four tools or conclude. This is an explicit investigation policy, not evidence that the model spontaneously chose to inspect code. File reads support line ranges, capped at 200 lines / 8,000 characters. Provider failures, context/output limits, malformed JSON, and unseen citations yield `status=incomplete` and a reason. `status=complete` only means the output satisfied the protocol and evidence-path checks; it does **not** certify the diagnosis.

Stop terminal A with Ctrl+C when done to release model memory.

## 4. Use the same model through FastAPI / LangGraph

With the local model server running:

```bash
export REPOPILOT_ALLOWED_ROOT=/absolute/path/to/workspace
export REPOPILOT_INVESTIGATION_PROVIDER=local
export REPOPILOT_INVESTIGATION_MODEL=qwen3-4b
export REPOPILOT_LOCAL_MODEL_URL=http://127.0.0.1:8081/v1
# Optional: python -m pip install -e '.[graph]'
export REPOPILOT_INVESTIGATION_WORKFLOW=langgraph
uvicorn repopilot.api.app:app --host 127.0.0.1 --port 8000
```

Index a repository and call `/investigate` as described in the README. You can leave the embedding provider at `none`: BM25 plus a local LLM already exercises the full investigation loop. To compare retrieval methods, enable the embedding and reranker settings separately. The lightweight Docker image does not bundle the LLM/runtime; the tested no-key model route is the host process setup above.

## Failure cases

- **Connection unavailable**: start llama-server and check `curl --noproxy '*' http://127.0.0.1:8081/health`.
- **HTTP 400 / context too long**: inspect the local server log. Tool outputs and call count are bounded, but accumulated history can still exceed the context. The API returns an incomplete investigation rather than a claimed diagnosis.
- **Tool/output limit**: retain the trace and rerun a narrower issue. Raising the budget may consume more context without improving the answer.
- **Wrong diagnosis**: inspect the cited source and proposed tests. The small local model can produce plausible but incorrect causal explanations.

See `evaluation/LOCAL_MODEL_REPORT.md` for measured results and limitations.

V0.9 also assembles a final report in one tool-free request with a JSON schema over actual source reads, preserving the draft separately. This can happen when the configured tool budget is reached. The resulting citation ranges are checked against the source actually returned to the model; missing or unread evidence is marked for review. This is an additional local inference call, with a 2,200-token output cap, and can increase latency. It does not run tests or certify a root cause.
