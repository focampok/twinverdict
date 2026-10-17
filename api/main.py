"""API: salud, tarjeta de operador, aprobación y probador de políticas."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, text
from starlette.middleware.gzip import GZipMiddleware
from starlette.templating import Jinja2Templates
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from api import live
from api.operator import (
    DecisionLog,
    efficiency_rows,
    load_efficiency,
    load_replay,
    operator_context,
    stamp_approval,
    winning_policy_id,
)
from api.try_policy import (
    GANTT_SEED,
    TIMEOUT_S,
    PolicyLab,
    RateLimiter,
    TryPolicyError,
    controls,
    policy_from_form,
    validate_policy,
)
from config import Settings

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = Jinja2Templates(directory=str(ROOT / "ui" / "templates"))
LOG = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    try:
        app.state.lab = PolicyLab(settings.REPLAY_JOB_ID, settings.SIM_WORKERS)
        await app.state.lab.references()
    except (FileNotFoundError, KeyError, ValueError) as exc:
        LOG.warning("try-a-policy references unavailable: %s", exc)
    try:
        yield
    finally:
        if app.state.lab is not None:
            app.state.lab.close()


def create_app(database_url: str | None = None) -> FastAPI:
    app = FastAPI(title="TwinVerdict", lifespan=_lifespan)
    app.state.database_url = database_url
    app.state.decisions = DecisionLog()
    app.state.lab = None
    app.state.try_limiter = RateLimiter()
    app.state.try_timeout_s = TIMEOUT_S
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    # Railway termina TLS en su proxy; sin esto request.base_url sale con http://.
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
    app.mount("/visual", StaticFiles(directory=ROOT / "netlify-visual"), name="visual")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(ROOT / "netlify-visual" / "favicon.svg", media_type="image/svg+xml")

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
        lab: PolicyLab | None = app.state.lab
        page["try_presets"] = (
            None if lab is None else {"fixed": controls(lab.fixed), "llm": controls(lab.llm)}
        )
        return TEMPLATES.TemplateResponse(request, "operator.html", page)

    @app.get("/live")
    def live_page(request: Request):
        settings = Settings()
        page = _live_context(settings.MODE, settings.REPLAY_JOB_ID, None, live.DEFAULT_SPEED)
        return TEMPLATES.TemplateResponse(request, "live.html", page)

    @app.get("/live/frame")
    def live_frame(request: Request, pos: str = "0", speed: str = ""):
        settings = Settings()
        page = _live_context(
            settings.MODE,
            settings.REPLAY_JOB_ID,
            live.parse_position(pos),
            live.parse_speed(speed or live.DEFAULT_SPEED),
        )
        return TEMPLATES.TemplateResponse(request, "live_frame.html", page)

    @app.post("/api/try-policy")
    async def try_policy(request: Request) -> Response:
        htmx = request.headers.get("HX-Request") == "true"
        started = time.perf_counter()
        try:
            if not app.state.try_limiter.allow(_client_key(request)):
                raise TryPolicyError(
                    429, "Too many simulations, please wait a minute and try again."
                )
            lab: PolicyLab | None = app.state.lab
            if lab is None:
                raise TryPolicyError(503, "The reference policies are not loaded.")
            policy = validate_policy(await _policy_payload(request))
            references = await lab.references()
            try:
                user = await asyncio.wait_for(lab.evaluate(policy), app.state.try_timeout_s)
            except TimeoutError:
                raise TryPolicyError(504, "Simulation timed out, try a simpler policy.") from None
        except TryPolicyError as exc:
            if htmx:
                return TEMPLATES.TemplateResponse(
                    request, "try_error.html", {"message": exc.message}, status_code=exc.status
                )
            return JSONResponse({"detail": exc.message}, status_code=exc.status)
        payload = _try_payload(lab, user, references)
        timing = {"Server-Timing": f"sim;dur={(time.perf_counter() - started) * 1000:.0f}"}
        if htmx:
            return TEMPLATES.TemplateResponse(request, "try_result.html", payload, headers=timing)
        return JSONResponse(payload, headers=timing)

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


_SEARCH_KEYS = ("phase", "round", "rounds_total", "proposals", "simulations", "best_objective")


def _live_context(mode: str, job_id: str, position: float | None, speed: int) -> dict:
    """En replay avanza `speed` segundos de grabación por segundo; en live muestra lo último."""
    recording = live.replay_recording(job_id) if mode == "replay" else live.current_recording()
    page: dict[str, Any] = {
        "mode": mode,
        "recording": recording,
        "speed": speed,
        "speeds": live.SPEEDS,
        "polling": False,
    }
    if recording is None:
        # MODE=live: seguir pidiendo el frame hasta que el worker cree el JSON.
        if mode != "replay":
            page["polling"] = True
            page["next_pos"] = 0.0
        return page
    if mode == "replay":
        at = 0.0 if position is None else position
        polling = at < live.duration(recording)
        next_pos = live.next_position(at, speed)
    else:
        at = live.duration(recording)
        polling = recording.get("status") == "running"
        next_pos = at
    shown = live.frame(recording, at)
    event = shown["event"] or {}
    page.update(
        frame=shown,
        polling=polling,
        next_pos=next_pos,
        search=dict.fromkeys(_SEARCH_KEYS) | (event.get("search") or {}),
        vllm=dict.fromkeys(("tokens_per_s", "requests_running")) | (event.get("vllm") or {}),
        gpu=dict.fromkeys(("use_pct", "vram_pct", "power_w")) | (event.get("gpu") or {}),
        recorded_at=live.clock(event.get("ts")),
        started_at=live.clock(recording.get("started_at")),
        model=live.model_label(recording.get("model")),
    )
    return page


def _client_key(request: Request) -> str:
    """El último salto de X-Forwarded-For lo pone el proxy; los anteriores, el cliente."""
    forwarded = request.headers.get("x-forwarded-for", "")
    hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
    if hops:
        return hops[-1]
    return request.client.host if request.client else "unknown"


async def _policy_payload(request: Request) -> object:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            return json.loads(await request.body())
        except json.JSONDecodeError:
            raise TryPolicyError(422, "The body is not valid JSON.") from None
    if "application/x-www-form-urlencoded" in content_type:
        form = parse_qs((await request.body()).decode(), keep_blank_values=True)
        return policy_from_form({key: values[0] for key, values in form.items()})
    raise TryPolicyError(422, "Send the policy as JSON or as the UI form.")


def _try_payload(lab: PolicyLab, user: dict[str, Any], references: dict[str, Any]) -> dict:
    return {
        "seeds": lab.seeds,
        "official_seeds": lab.official_seeds,
        "gantt_seed": GANTT_SEED,
        "rows": [
            {"key": "user", "label": "Your policy", **user["summary"]},
            {"key": "fixed", "label": "Fixed rule", **references["fixed"]["summary"]},
            {
                "key": "llm",
                "label": "LLM best policy (recorded run)",
                **references["llm"]["summary"],
            },
        ],
        "gantt": {"baseline": references["fixed"]["gantt"], "proposed": user["gantt"]},
    }


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
