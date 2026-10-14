ifneq (,$(wildcard .env))
include .env
export
endif

.PHONY: setup db mock-llm web worker dev test lint bench enqueue-baseline enqueue-search search-mock baseline-optuna baseline-llm-nf efficiency docker-build

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

docker-build:
	docker build -t planta .
