#!/usr/bin/env bash
# Worker nativo en tmux. vLLM se usa por localhost; la BD es la de Railway.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ENV_FILE="${SCRIPT_DIR}/.env.gpu"
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "falta ${ENV_FILE}" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

: "${DATABASE_URL:?DATABASE_URL es obligatoria}"
: "${LLM_MODEL:?LLM_MODEL es obligatorio}"
: "${VLLM_API_KEY:?VLLM_API_KEY es obligatoria}"
LLM_BASE_URL="${LLM_BASE_URL:-http://127.0.0.1:8000/v1}"
LLM_API_KEY="${LLM_API_KEY:-${VLLM_API_KEY}}"
workers=$(($(nproc) - 2))
if ((workers < 1)); then
  workers=1
fi

REPO_DIR="${REPO_DIR:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
if tmux has-session -t worker 2>/dev/null; then
  echo "la sesión tmux worker ya existe"
  exit 0
fi

tmux new-session -d -s worker -c "${REPO_DIR}" \
  "export DATABASE_URL=$(printf '%q' "${DATABASE_URL}") \
LLM_BASE_URL=$(printf '%q' "${LLM_BASE_URL}") \
LLM_MODEL=$(printf '%q' "${LLM_MODEL}") \
LLM_API_KEY=$(printf '%q' "${LLM_API_KEY}") \
SIM_WORKERS=${workers}; exec uv run python -m worker.main"
echo "worker en tmux (sesión worker), SIM_WORKERS=${workers}"
