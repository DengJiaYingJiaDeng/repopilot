#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
python_bin="${REPOPILOT_PYTHON:-${project_root}/.venv/bin/python}"
frontend_port="${FRONTEND_PORT:-5173}"
backend_port="${BACKEND_PORT:-8000}"
model_port="${MODEL_PORT:-18081}"
logs_dir="${project_root}/.local/workbench"
mkdir -p "$logs_dir"
if [[ ! -x "$python_bin" ]] || ! command -v node >/dev/null || ! command -v pnpm >/dev/null; then
  echo '缺少 Python 虚拟环境、Node.js 或 pnpm，请先阅读 docs/WEB_WORKBENCH.md。' >&2
  exit 1
fi
"$python_bin" - "$frontend_port" "$backend_port" "$model_port" <<'PY'
import socket,sys
ports=list(map(int,sys.argv[1:]))
if len(set(ports)) != 3:
    raise SystemExit('前端、后端、模型端口必须不同。')
for port in ports:
    try:
        with socket.socket() as s:
            s.bind(('127.0.0.1',port))
    except OSError:
        raise SystemExit(f'端口 {port} 已被占用。请先关闭之前启动的工作台，再重新运行。')
PY
if [[ ! -d frontend/node_modules ]]; then
  pnpm --dir frontend install --frozen-lockfile
fi
echo '正在准备可视化页面…'
VITE_API_BASE_URL="http://127.0.0.1:${backend_port}" pnpm --dir frontend build > "$logs_dir/frontend-build.log" 2>&1 || { cat "$logs_dir/frontend-build.log"; exit 1; }
pids=()
cleanup() {
  trap - EXIT INT TERM
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
  for pid in "${pids[@]}"; do wait "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT INT TERM
MODEL_PORT="$model_port" bash scripts/start_local_model.sh > "$logs_dir/model.log" 2>&1 &
pids+=("$!")
REPOPILOT_ALLOWED_ROOT="${REPOPILOT_ALLOWED_ROOT:-${project_root}/..}" \
REPOPILOT_INVESTIGATION_PROVIDER=local REPOPILOT_INVESTIGATION_MODEL=qwen3-4b \
REPOPILOT_LOCAL_MODEL_URL="http://127.0.0.1:${model_port}/v1" \
REPOPILOT_INVESTIGATION_WORKFLOW=langgraph \
REPOPILOT_CORS_ORIGINS="[\"http://127.0.0.1:${frontend_port}\",\"http://localhost:${frontend_port}\"]" \
"$python_bin" -m uvicorn repopilot.api.app:app --host 127.0.0.1 --port "$backend_port" > "$logs_dir/backend.log" 2>&1 &
pids+=("$!")
node frontend/node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port "$frontend_port" --strictPort --config frontend/vite.config.ts --outDir "$project_root/frontend/dist" > "$logs_dir/frontend.log" 2>&1 &
pids+=("$!")
ready=false
for ((attempt=0; attempt<60; attempt++)); do
  for pid in "${pids[@]}"; do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "服务启动失败。日志位于 ${logs_dir}。" >&2
      tail -n 6 "$logs_dir/model.log" "$logs_dir/backend.log" "$logs_dir/frontend.log"
      exit 1
    fi
  done
  if curl --noproxy '*' -fsS --max-time 1 "http://127.0.0.1:${model_port}/health" >/dev/null 2>&1 && \
     curl --noproxy '*' -fsS --max-time 1 "http://127.0.0.1:${backend_port}/health" >/dev/null 2>&1 && \
     curl --noproxy '*' -fsS --max-time 1 "http://127.0.0.1:${frontend_port}/" >/dev/null 2>&1; then
    ready=true; break
  fi
  sleep 1
done
if [[ "$ready" != true ]]; then
  echo "服务启动超时，请查看 ${logs_dir} 中的日志。" >&2
  exit 1
fi
echo "RepoPilot 工作台已就绪：http://127.0.0.1:${frontend_port}"
echo '在浏览器打开上面的地址。先看示例，或点击右上角“导入报告”。'
echo '保持这个终端打开。使用结束后按 Ctrl+C，将自动关闭本次启动的三个服务。'
wait -n "${pids[@]}" || true
