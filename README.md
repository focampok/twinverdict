# twinverdict

Gemelo simulado de una línea de producción con 5 máquinas y 3 productos.
Un LLM propone políticas de mantenimiento y despacho en JSON validado.
El simulador las mide sobre muchas semillas; el número lo da el simulador, nunca el modelo.

## Requisitos

Python 3.12, [uv](https://docs.astral.sh/uv/) y Postgres nativo con la misma versión mayor que el Postgres de Railway. Hoy el local y el CI usan la 16; confírmalo en Railway antes del despliegue.

## Correr en local

Una sola vez, con Postgres ya instalado:

```bash
sudo -u postgres psql -c "CREATE ROLE planta LOGIN PASSWORD 'planta' CREATEDB;"
```

Después:

```bash
cp .env.example .env
make setup
make db
make dev
```

`make dev` levanta el mock LLM (puerto 8001), la web (puerto 8000) y el worker. Por separado: `make mock-llm`, `make web`, `make worker`.

Tests y benchmark:

```bash
make test
make lint
make bench
```

## Variables de entorno

Están en `.env.example`: `DATABASE_URL`, `MODE` (`live` o `replay`), `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `ADMIN_TOKEN`, `SIM_WORKERS`.

Para apuntar a un vLLM propio basta cambiar `LLM_BASE_URL`, `LLM_MODEL` y `LLM_API_KEY`. El cliente es el de `llm/client.py`, compatible con OpenAI.

## Docker

Docker solo se usa para la imagen de Railway (`Dockerfile`, `railway.toml`). No hay `docker-compose.yml`. El desarrollo y los tests corren nativos.

## Licencia y alcance

Licencia MIT. Es una planta simulada, no una fábrica real.

Todo el código se escribió durante el hackathon, a partir del lunes 12 de octubre de 2026, después del kickoff.
