#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
models_dir="${REPOPILOT_MODELS_DIR:-${project_root}/../repopilot-models}"
llama_server="${LLAMA_SERVER:-${models_dir}/llama-runtime/llama-b11382/llama-server}"
model_path="${MODEL_PATH:-${models_dir}/qwen3-4b/Qwen3-4B-Q4_K_M.gguf}"
if [[ ! -x "$llama_server" || ! -f "$model_path" ]]; then
  echo "Local runtime or model is missing. See docs/LOCAL_MODELS.md." >&2
  exit 1
fi
exec "$llama_server" -m "$model_path" --alias qwen3-4b \
  --host 127.0.0.1 --port "${MODEL_PORT:-8081}" \
  -c "${CONTEXT_SIZE:-16384}" -ngl "${GPU_LAYERS:-99}" -np 1 --jinja --reasoning off
