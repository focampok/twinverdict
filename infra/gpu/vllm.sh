#!/usr/bin/env bash
# vLLM solo en 127.0.0.1. Nunca 0.0.0.0.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
if [[ -f "${SCRIPT_DIR}/.env.gpu" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/.env.gpu"
  set +a
fi

# fijar el tag exacto que funcione hoy
VLLM_IMAGE="${VLLM_IMAGE:-rocm/vllm:latest}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-8192}"
GPU_MEM_UTIL="${GPU_MEM_UTIL:-0.90}"
VLLM_PORT="${VLLM_PORT:-8000}"
VLLM_WAIT_TIMEOUT="${VLLM_WAIT_TIMEOUT:-300}"
HF_HOME="${HF_HOME:-${HOME}/hf-cache}"
VLLM_API_KEY="${VLLM_API_KEY:-}"
MODEL="${MODEL:-}"

usage() {
  echo "uso: $0 {start|stop|logs|status}" >&2
  exit 1
}

wait_ready() {
  if ! command -v curl >/dev/null 2>&1; then
    echo "curl es necesario para esperar /v1/models" >&2
    exit 1
  fi
  local deadline
  deadline=$((SECONDS + VLLM_WAIT_TIMEOUT))
  while (( SECONDS < deadline )); do
    if curl -fsS -H "Authorization: Bearer ${VLLM_API_KEY}" \
      "http://127.0.0.1:${VLLM_PORT}/v1/models" >/dev/null; then
      echo "vLLM responde en 127.0.0.1:${VLLM_PORT}"
      return 0
    fi
    sleep 2
  done
  echo "vLLM no respondió a tiempo" >&2
  docker logs vllm || true
  exit 1
}

start() {
  if [[ -z "${VLLM_API_KEY}" ]]; then
    echo "VLLM_API_KEY es obligatoria" >&2
    exit 1
  fi
  if [[ -z "${MODEL}" ]]; then
    echo "MODEL es obligatorio" >&2
    exit 1
  fi
  if docker ps --filter "name=^vllm$" --format '{{.Names}}' | grep -qx vllm; then
    echo "vllm ya está corriendo"
    exit 0
  fi
  docker rm -f vllm >/dev/null 2>&1 || true
  mkdir -p "${HF_HOME}"
  local -a env_args=()
  if [[ -n "${HF_TOKEN:-}" ]]; then
    env_args+=(-e "HF_TOKEN=${HF_TOKEN}")
  fi
  docker run -d --name vllm \
    --device=/dev/kfd \
    --device=/dev/dri \
    --group-add video \
    --ipc=host \
    --security-opt seccomp=unconfined \
    --network=host \
    -e "HF_HOME=/root/.cache/huggingface" \
    "${env_args[@]}" \
    -v "${HF_HOME}:/root/.cache/huggingface" \
    "${VLLM_IMAGE}" \
    vllm serve "${MODEL}" \
    --host 127.0.0.1 \
    --port "${VLLM_PORT}" \
    --api-key "${VLLM_API_KEY}" \
    --max-model-len "${MAX_MODEL_LEN}" \
    --gpu-memory-utilization "${GPU_MEM_UTIL}"
  wait_ready
}

cmd="${1:-}"
case "${cmd}" in
  start) start ;;
  stop) docker rm -f vllm ;;
  logs) docker logs -f vllm ;;
  status) docker ps -a --filter "name=vllm" ;;
  *) usage ;;
esac
