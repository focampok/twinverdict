FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /uvx /bin/

WORKDIR /app
RUN useradd --create-home --uid 10001 app

COPY pyproject.toml uv.lock README.md LICENSE alembic.ini ./
COPY config.py ./
COPY sim sim
COPY policy policy
COPY search search
COPY llm llm
COPY eval eval
COPY baselines baselines
COPY guard guard
COPY api api
COPY ui ui
COPY db db
COPY worker worker
COPY bench bench

RUN uv sync --frozen --no-dev && chown -R app:app /app
USER app

ENV PATH="/app/.venv/bin:${PATH}"
ENV PORT=8000

# Web por defecto. El worker usa la misma imagen con: python -m worker.main
CMD ["sh", "-c", "alembic upgrade head && uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
