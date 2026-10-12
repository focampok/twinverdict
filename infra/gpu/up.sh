#!/usr/bin/env bash
# Se corre en la instancia recién creada. No arranca vLLM ni el worker.
set -euo pipefail

if command -v rocm-smi >/dev/null 2>&1; then
  rocm-smi
elif command -v amd-smi >/dev/null 2>&1; then
  amd-smi
else
  echo "rocm-smi/amd-smi no disponible en esta máquina"
fi
echo "nproc=$(nproc)"

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="${HOME}/.local/bin:${PATH}"
fi

: "${REPO_URL:?definir REPO_URL}"
REPO_DIR="${REPO_DIR:-${HOME}/twinverdict}"
if [[ -d "${REPO_DIR}/.git" ]]; then
  git -C "${REPO_DIR}" pull --ff-only
else
  git clone "${REPO_URL}" "${REPO_DIR}"
fi
(
  cd "${REPO_DIR}"
  uv sync
)

if ! command -v tmux >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y tmux
fi

cat <<EOF
No se arrancó ningún servicio. Siguientes comandos:
  cd ${REPO_DIR}
  cp infra/gpu/.env.gpu.example infra/gpu/.env.gpu
  # editar .env.gpu; no lo subas al repo
  ./infra/gpu/vllm.sh start
  ./infra/gpu/worker.sh
EOF
