#!/usr/bin/env bash
# shellcheck disable=SC2016,SC2029
# TwinVerdict: control de la GPU MI300X sin terminales bloqueadas.
# Uso: infra/gpu/gpu.sh <comando> [args]
#   tunnel        abre el túnel SSH en segundo plano (localhost:8000)
#   untunnel      cierra el túnel
#   status        GPU, proceso vLLM y modelo cargado
#   smi           JSON de rocm-smi (uso, VRAM, potencia, nombre); reusa el túnel si está abierto
#   serve MODELO  cambia el modelo (mata vLLM y lo relanza con la misma api-key)
#   wait          espera hasta que /v1/models responda (máx 15 min)
#   logs [N]      últimas N líneas del log de vLLM (default 40)
#   stop          detiene vLLM
#   bench-sim     benchmark sostenido de simulación en la instancia (20 vCPU, 18 workers)
#   run "cmd"     ejecuta un comando en la GPU
set -euo pipefail
GPU_IP="${GPU_IP:-129.212.185.2}"
GPU_USER="${GPU_USER:-root}"
PORT="${VLLM_PORT:-8000}"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=30 -o StrictHostKeyChecking=accept-new)
SOCK="/tmp/twinverdict-gpu-tunnel.sock"
r() { ssh "${SSH_OPTS[@]}" "$GPU_USER@$GPU_IP" "$@"; }

case "${1:-}" in
  tunnel)
    if [ -S "$SOCK" ] && ssh -S "$SOCK" -O check "$GPU_USER@$GPU_IP" 2>/dev/null; then echo "Túnel ya activo."; exit 0; fi
    ssh "${SSH_OPTS[@]}" -M -S "$SOCK" -f -N -L "$PORT:localhost:$PORT" "$GPU_USER@$GPU_IP"
    echo "Túnel activo: http://localhost:$PORT/v1" ;;
  untunnel)
    ssh -S "$SOCK" -O exit "$GPU_USER@$GPU_IP" 2>/dev/null && echo "Túnel cerrado." || echo "No había túnel." ;;
  smi)
    SMI='rocm-smi --showuse --showmemuse --showpower --showproductname --json'
    if [ -S "$SOCK" ] && ssh -S "$SOCK" -O check "$GPU_USER@$GPU_IP" 2>/dev/null; then
      ssh -S "$SOCK" "${SSH_OPTS[@]}" "$GPU_USER@$GPU_IP" "$SMI"
    else
      r "$SMI"
    fi ;;
  status)
    r 'rocm-smi --showuse --showmemuse | grep -E "^[0-9]|GPU" ; echo "--- vLLM:"; docker exec rocm pgrep -af "vllm serve" | sed -E "s/--api-key [^ ]+/--api-key ***/" || echo "(no corre)"; echo "--- modelo:"; curl -s localhost:'"$PORT"'/v1/models -H "Authorization: Bearer $(cat /root/vllm.key)" | python3 -c "import sys,json;d=json.load(sys.stdin);print([m[\"id\"] for m in d.get(\"data\",[])] or d)" 2>/dev/null || echo "(sin respuesta)"' ;;
  serve)
    MODEL="${2:?Indica el modelo, ej: Qwen/Qwen3-32B}"; EXTRA="${3:-}"
    r "docker exec rocm pkill -f 'vllm serve' || true; sleep 5; docker exec -d rocm sh -c \"vllm serve $MODEL --port $PORT --api-key \$(cat /root/vllm.key) $EXTRA > /tmp/vllm.log 2>&1\""
    echo "Lanzado $MODEL. Usa: $0 wait" ;;
  wait)
    for _ in $(seq 1 90); do
      out=$(r 'curl -s -o /dev/null -w "%{http_code}" localhost:'"$PORT"'/v1/models -H "Authorization: Bearer $(cat /root/vllm.key)"' || true)
      [ "$out" = "200" ] && { echo "vLLM listo."; exit 0; }
      if ! r 'docker exec rocm pgrep -f "vllm serve" >/dev/null'; then echo "vLLM se cayó. Últimas líneas:"; r 'docker exec rocm tail -n 30 /tmp/vllm.log'; exit 1; fi
      sleep 10
    done; echo "Timeout (15 min)."; exit 1 ;;
  logs) r "docker exec rocm tail -n ${2:-40} /tmp/vllm.log" ;;
  stop) r "docker exec rocm pkill -f 'vllm serve' || true"; echo "vLLM detenido." ;;
  bench-sim)
    r 'repo="${GPU_REPO:-$HOME/twinverdict}"; test -d "$repo" || { echo "no está el repo en $repo"; exit 1; }; cd "$repo" && uv run python -m bench.sim_speed --seeds 300 --workers 18 --repeat 6' ;;
  run)  shift; r "$@" ;;
  *) sed -n '2,13p' "$0"; exit 1 ;;
esac
