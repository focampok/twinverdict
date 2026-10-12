"""API mínima: salud, readiness y un placeholder de la UI."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from starlette.templating import Jinja2Templates

from config import Settings

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "ui" / "templates"))


def create_app(database_url: str | None = None) -> FastAPI:
    app = FastAPI(title="TwinVerdict")
    app.state.database_url = database_url

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
        return TEMPLATES.TemplateResponse(
            request,
            "index.html",
            {"mode": Settings().MODE},
        )

    return app


app = create_app()
