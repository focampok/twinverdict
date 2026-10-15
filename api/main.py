"""API: salud, tarjeta de operador y aprobación."""

from __future__ import annotations

import json
import secrets
import uuid
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from starlette.templating import Jinja2Templates

from api.operator import (
    DecisionLog,
    efficiency_rows,
    load_efficiency,
    load_replay,
    operator_context,
    stamp_approval,
    winning_policy_id,
)
from config import Settings

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "ui" / "templates"))


def create_app(database_url: str | None = None) -> FastAPI:
    app = FastAPI(title="TwinVerdict")
    app.state.database_url = database_url
    app.state.decisions = DecisionLog()

    @app.middleware("http")
    async def replay_only(request: Request, call_next):
        if _replay_blocks(request.method, request.url.path):
            return JSONResponse({"error": "replay_only"}, status_code=503)
        return await call_next(request)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> JSONResponse:
        url = app.state.database_url or Settings().DATABASE_URL
        engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 2})
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return JSONResponse({"status": "ok"})
        except Exception:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        finally:
            engine.dispose()

    @app.get("/")
    def index(request: Request):
        settings = Settings()
        policy_id = winning_policy_id(settings.REPLAY_JOB_ID)
        decision = app.state.decisions.get(policy_id) if policy_id else None
        page = operator_context(settings.REPLAY_JOB_ID, settings.MODE, decision)
        try:
            page["efficiency_rows"] = efficiency_rows(load_efficiency())
        except (FileNotFoundError, json.JSONDecodeError):
            page["efficiency_rows"] = []
        return TEMPLATES.TemplateResponse(request, "operator.html", page)

    @app.get("/api/efficiency")
    def efficiency() -> JSONResponse:
        try:
            payload = load_efficiency()
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="not found") from None
        return JSONResponse(payload)

    @app.get("/api/replay/{job_id}")
    def replay(job_id: uuid.UUID) -> JSONResponse:
        try:
            payload = load_replay(job_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="not found") from None
        return JSONResponse(payload)

    @app.post("/jobs")
    def create_job() -> JSONResponse:
        from worker.enqueue import enqueue

        return JSONResponse({"job_id": enqueue("search")})

    @app.post("/policies/{policy_id}/approve")
    async def approve(policy_id: uuid.UUID, request: Request):
        return await _decide(policy_id, request, "approved")

    @app.post("/policies/{policy_id}/reject")
    async def reject(policy_id: uuid.UUID, request: Request):
        return await _decide(policy_id, request, "rejected")

    async def _decide(
        policy_id: uuid.UUID,
        request: Request,
        status: Literal["approved", "rejected"],
    ):
        _require_admin(request)
        reason = await _reason(request)
        key = str(policy_id)
        app.state.decisions.record(key, status, reason)
        stamp_approval(app.state.database_url, key, approved=status == "approved")
        settings = Settings()
        page = operator_context(
            settings.REPLAY_JOB_ID,
            settings.MODE,
            app.state.decisions.get(key),
        )
        page["policy_id"] = key
        return TEMPLATES.TemplateResponse(request, "decision.html", page)

    return app


def _replay_blocks(method: str, path: str) -> bool:
    """En replay se lee la corrida congelada. Encolar o llamar al LLM no está disponible."""
    if Settings().MODE != "replay":
        return False
    normalized = path.rstrip("/") or "/"
    return method == "POST" and normalized == "/jobs"


def _require_admin(request: Request) -> None:
    expected = Settings().ADMIN_TOKEN
    if not expected:
        return
    got = request.headers.get("ADMIN_TOKEN", "")
    if not secrets.compare_digest(got, expected):
        raise HTTPException(status_code=401, detail="unauthorized")


async def _reason(request: Request) -> str | None:
    raw = await request.body()
    if not raw:
        return None
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="invalid json") from exc
        if not isinstance(payload, dict):
            return None
        reason = payload.get("reason")
        return str(reason) if reason else None
    if "application/x-www-form-urlencoded" in content_type:
        parsed = parse_qs(raw.decode())
        reason = parsed.get("reason", [None])[0]
        return reason or None
    return None


app = create_app()
