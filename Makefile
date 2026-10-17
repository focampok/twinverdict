ifneq (,$(wildcard .env))
include .env
export
endif

.PHONY: setup db mock-llm web worker dev test lint bench enqueue-baseline enqueue-search search-mock baseline-optuna baseline-llm-nf efficiency gpu2 docker-build

setup:
	uv sync

db:
	uv run python -c "import os,subprocess,sys; from urllib.parse import urlparse; raw=os.environ['DATABASE_URL'].replace('+psycopg','',1); u=urlparse(raw); name=u.path.lstrip('/').split('?',1)[0]; env=os.environ.copy(); env['PGPASSWORD']=u.password or ''; host=u.hostname or 'localhost'; port=str(u.port or 5432); user=u.username or 'planta'; check=subprocess.run(['psql','-h',host,'-p',port,'-U',user,'-d',name,'-c','SELECT 1'], env=env, capture_output=True); sys.exit(0 if check.returncode==0 else subprocess.run(['createdb','-h',host,'-p',port,'-U',user,name], env=env).returncode)"
	uv run alembic upgrade head

mock-llm:
	uv run uvicorn llm.mock_server:app --host 127.0.0.1 --port 8001

web:
	uv run uvicorn api.main:app --reload --port 8000

worker:
	uv run python -m worker.main

dev:
	uv run honcho start -f Procfile.dev

test:
	uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format --check .

bench:
	uv run python -m bench.sim_speed --seeds 50

enqueue-baseline:
	uv run python -m worker.enqueue baseline

enqueue-search:
	uv run python -m worker.enqueue search

search-mock:
	uv run python -m search.loop --seed 1

baseline-optuna:
	uv run python -m baselines.optuna_search --profile default --seed 1

baseline-llm-nf:
	uv run python -m baselines.llm_nofeedback --profile default --seed 1

efficiency:
	uv run python -m eval.efficiency --results-dir bench/results --profile default --seed 1

# Sesión GPU 2: vLLM por túnel SSH en localhost:8000, simulaciones en la laptop.
# Requisitos y pasos completos en docs/dev-log/SESION_GPU2.md. La GPU solo sirve vLLM.
GPU2_PROFILE ?= default
GPU2_SEED ?= 1
GPU2_HOLDOUT ?= 300
GPU2_WORKERS ?= 16
GPU2_BASE_URL ?= http://127.0.0.1:8000/v1
GPU2_MODEL ?= Qwen/Qwen3-8B

gpu2:
	@set -e; \
	export LLM_BASE_URL="$(GPU2_BASE_URL)"; \
	export LLM_MODEL="$(GPU2_MODEL)"; \
	test -n "$$LLM_API_KEY" || { echo "falta LLM_API_KEY: es la api-key de vLLM de esta sesión"; exit 1; }; \
	if pgrep -f "[m]ock_server" >/dev/null; then echo "el mock sigue arriba en el 8001: páralo antes de medir contra vLLM"; exit 1; fi; \
	curl -sf -o /dev/null -H "Authorization: Bearer $$LLM_API_KEY" "$$LLM_BASE_URL/models" \
		|| { echo "vLLM no responde en $$LLM_BASE_URL: abre el túnel con infra/gpu/gpu.sh tunnel"; exit 1; }; \
	echo "=== bucle $(GPU2_PROFILE) seed $(GPU2_SEED) holdout $(GPU2_HOLDOUT) vía worker, $(GPU2_WORKERS) workers en la laptop"; \
	job=$$(uv run python -m worker.enqueue search --profile $(GPU2_PROFILE) --seed $(GPU2_SEED) --scenario base --holdout $(GPU2_HOLDOUT)); \
	echo "job $$job"; \
	SIM_WORKERS=$(GPU2_WORKERS) uv run python -m worker.main --drain; \
	echo "=== LLM sin retroalimentación, mismo presupuesto y semillas"; \
	SIM_WORKERS=$(GPU2_WORKERS) uv run python -m baselines.llm_nofeedback --profile $(GPU2_PROFILE) --seed $(GPU2_SEED); \
	echo "=== replay congelado y tabla de los cuatro métodos"; \
	uv run python -m search.freeze_run $$job; \
	uv run python -m eval.efficiency --results-dir bench/results --profile $(GPU2_PROFILE) \
		--seed $(GPU2_SEED) --workers $(GPU2_WORKERS) \
		--loop-json bench/results/replay_$$job.json --require-llm-source vllm

docker-build:
	docker build -t planta .
