# TwinVerdict: prompts del lunes 12 oct, desde cero (13:00 a 22:00 GT)

Reemplaza a `prompts-domingo-linea-base.md` y `prompts-lunes-gpu.md`. Plan de referencia: `twinverdict-plan-v4.md` (fila "Lun 12" de la sección 10).

**Objetivo de hoy:** desde un repo vacío, dejar la línea base completa y sin GPU: repo en GitHub y scaffolding, esquema de la política, simulador v0 determinista, `simulate()` con KPIs, mock LLM y `LLMClient`, Postgres nativo con Alembic, worker stub, `Makefile` y CI en verde. Si sobra tiempo: scripts de la instancia, smoke JSON y harness de benchmarks, todo contra el mock.

**Sin GPU hoy**, salvo que a las 22:00 la línea base esté completa y el precio por hora esté confirmado en la consola. Si no, la primera sesión de GPU es el martes en la mañana.

Convención de entorno (igual que el plan v4): desarrollo nativo en tu Linux, sin docker compose. Postgres del sistema, mock LLM con `uvicorn`, web y worker como procesos locales, `Makefile` y `honcho`. Docker solo para la imagen de Railway.

## Agenda del día

| Hora (GT) | Paso | Prioridad |
|---|---|---|
| 13:00 a 13:30 | Paso 0 manual: repo, clon, plan y archivo de contexto | Obligatorio |
| 13:30 a 14:00 | Prompt 0: bootstrap del repo | Obligatorio |
| 14:00 a 14:45 | Prompt 1: esquema Pydantic de la política | Obligatorio |
| 14:45 a 16:15 | Prompt 2: simulador v0 (modelo de planta) | Obligatorio |
| 16:15 a 17:15 | Prompt 3: simulate(), KPIs, objetivo y benchmark | Obligatorio |
| 17:15 a 18:15 | Prompt 4: cliente LLM y mock compatible con OpenAI | Obligatorio |
| 18:30 a 19:30 | Prompt 5: base de datos, API mínima y worker stub | Obligatorio |
| 19:30 a 20:15 | Prompt 6: Makefile nativo, CI y Dockerfile solo para Railway | Obligatorio |
| 20:15 a 20:45 | Prompt 7: cierre de la línea base | Obligatorio |
| 20:45 a 21:15 | Prompt 8: scripts de la instancia (sin GPU) | Puede pasar al martes |
| 21:15 a 21:40 | Prompt 9: smoke test del LLM con JSON guiado (contra el mock) | Puede pasar al martes |
| 21:40 a 22:00 | Prompt 10: harness de benchmarks para fijar K y N (contra el mock) | Puede pasar al martes |

Si a las 20:45 todavía no terminaste el Prompt 6, salta directo al Prompt 7 y deja 8 a 10 para el martes en la mañana. Ese es el corte 1 del plan v4.

## Paso 0 manual (13:00 a 13:30)

1. **Crear el repo en GitHub** (después del kickoff, eso es justamente lo que se quiere mostrar): nombre `twinverdict`, público, licencia MIT, con README y `.gitignore` de Python. Con la CLI de GitHub:

   ```bash
   gh repo create twinverdict --public --license mit --gitignore Python --clone
   cd twinverdict
   ```

   (Si `gh` no agrega el README, se crea en el Prompt 0. Desde la web también vale: marca "Add a README", `.gitignore` Python y licencia MIT, y luego `git clone`.)

2. **Postgres local** (una sola vez, con Postgres ya instalado y corriendo):

   ```bash
   sudo -u postgres psql -c "CREATE ROLE planta LOGIN PASSWORD 'planta' CREATEDB;"
   psql --version   # anota la versión mayor; compárala luego con la del Postgres de Railway
   ```

   La base `planta` la crea `make db` (Prompt 6). Para los tests db del Prompt 5 basta con `createdb -h localhost -U planta planta`.

3. **Plan en el repo:** copia `twinverdict-plan-v4.md` como `docs/PLAN.md`.
4. **Archivo de contexto:** `CLAUDE.md` en la raíz (Claude Code) o `.cursor/rules/proyecto.mdc` (Cursor), con el texto de abajo.
5. **Primer commit y push:** `git add -A && git commit -m "docs: plan v4 y contexto del proyecto" && git push`.
6. **Método de pago en DigitalOcean:** si no está, agrégalo hoy (sin él no te deja crear la instancia el martes).

**Commits con hora clara.** Haz un commit por prompt con mensaje descriptivo (`git commit -m "prompt 2: simulador v0"`) y push frecuente. La historia de GitHub, con todas las fechas después del kickoff del lunes 12, es la prueba de que todo se hizo durante el hackathon. No reescribas la historia (nada de `rebase` ni `--amend` sobre commits ya subidos).

### Contenido del archivo de contexto

Para Cursor, empieza el archivo con este encabezado (para Claude Code omítelo):

```text
---
description: Contexto y reglas del proyecto TwinVerdict
alwaysApply: true
---
```

Cuerpo (igual para `CLAUDE.md` y `proyecto.mdc`):

```markdown
# TwinVerdict

## Qué es
Gemelo simulado (SimPy) de una línea de producción con 5 máquinas y 3 productos. Un LLM abierto
(vLLM en AMD MI300X, desde el martes) propone políticas de mantenimiento y despacho en JSON validado.
Ninguna política se recomienda sin probarla en el simulador sobre muchas semillas. El número lo da
el simulador, nunca el modelo. El producto termina en una tarjeta de operador: una recomendación
clara, con números verificados y aprobación humana. Plan completo: docs/PLAN.md (v4).

## Stack
Python 3.12, SimPy 4, NumPy, Pydantic v2, FastAPI, SQLAlchemy 2, Alembic, Postgres (misma versión
mayor que el servicio Postgres de Railway), SDK openai (async), pytest, ruff, GitHub Actions.
Gestor: uv (pyproject.toml + uv.lock). Docker solo para la imagen de Railway.

## Entornos
- Desarrollo nativo, sin docker compose; Docker solo para Railway. Postgres instalado en el
  sistema, mock LLM con uvicorn, web y worker como procesos locales, todo vía Makefile
  (setup, db, mock-llm, web, worker, dev, test, lint, bench) y honcho (Procfile.dev).
- CI: GitHub Actions con Postgres como services: del workflow.
- Producción: servicio Postgres administrado de Railway (DATABASE_URL referenciada desde el
  servicio). En la GPU, el worker corre nativo y usa la URL pública de Railway con
  sslmode=require; vLLM corre en su contenedor ROCm (única excepción), escucha en 127.0.0.1
  con --api-key y se usa por túnel SSH. Nunca se expone a internet.
- Entre entornos solo cambian variables (DATABASE_URL, LLM_BASE_URL, LLM_MODEL, LLM_API_KEY, MODE).
- Nunca crear docker-compose.yml ni dependencias de Docker para desarrollar o testear.

## Estructura
sim/ policy/ search/ llm/ eval/ baselines/ guard/ api/ ui/ db/ worker/ bench/ infra/gpu/ tests/ docs/

## Convenciones
- Type hints en todo el código público. ruff para lint y formato (line-length 100).
- Determinismo: toda aleatoriedad sale de numpy.random.Generator creado desde la semilla.
  Prohibido random global, np.random.* sin Generator, time.time() o el orden de dicts/sets
  como fuente de decisiones dentro de la simulación.
- La política es JSON validado con Pydantic, nunca código ejecutable.
- La configuración entra por variables de entorno (ver .env.example). Nunca secretos en el repo.
- El LLM siempre se usa a través de llm/client.py con interfaz compatible con OpenAI.
  Hoy se usa el mock; cambiar a vLLM real debe requerir solo cambiar LLM_BASE_URL y LLM_MODEL.
- Funciones pequeñas y puras donde se pueda; simulate(policy, seed) no toca red, disco ni BD.

## Alcance actual (lunes 12, desde cero)
Repo creado hoy después del kickoff. Hoy solo la línea base sin GPU: esquema, simulador v0,
simulate() y KPIs, mock LLM y LLMClient, BD con Alembic, API healthz/readyz, worker stub,
Makefile nativo y CI. Si sobra tiempo: infra/gpu/ (up.sh, vllm.sh, worker.sh), smoke de JSON
guiado y harness de benchmarks, todo probado contra el mock.
No implementar: vLLM real, Optuna, bucle de búsqueda, UI real, despliegue a Railway (solo se dejan
Dockerfile y railway.toml), SSE, autenticación, docker compose, nada de Google.
Si algo parece necesario y está fuera de alcance, deja un TODO y avísame; no lo construyas.

## Antes de decir "listo"
Ejecuta `uv run ruff check .`, `uv run ruff format --check .` y `uv run pytest -q`.
Reporta la salida real. Si algo falla, arréglalo o explica por qué no.
```

## Cómo usar los prompts

1. Pégalos **de uno en uno**, en orden. Después de cada uno: revisa el diff, corre `uv run pytest -q` y `uv run ruff check .` (o `make test` y `make lint` desde el Prompt 6), commit y push.
2. Si algo falla, pide la corrección en la misma conversación antes de seguir.
3. Si el agente se sale de lo pedido (UI, vLLM real, despliegue, Optuna, docker compose), detenlo y recuérdale la sección "No hagas".
4. Conversación nueva cada 2 o 3 prompts; el archivo de contexto y `docs/PLAN.md` mantienen la continuidad.
5. Respeta la caja de tiempo. Si un prompt se pasa más de 50%, acepta lo que funcione, deja un TODO y sigue.

---

## Prompt 0: bootstrap del repo

**Hora:** 13:30 a 14:00 (30 min) · **OBLIGATORIO HOY**

```text
Lee docs/PLAN.md completo y el archivo de contexto del proyecto (CLAUDE.md o .cursor/rules/proyecto.mdc).

Objetivo: dejar el esqueleto del repo listo para trabajar, sin lógica de negocio todavía.

Crea:
- Paquetes Python (con __init__.py): sim/, policy/, search/, llm/, eval/, baselines/, guard/,
  api/, ui/, db/, worker/, bench/. Carpeta tests/ con conftest.py vacío.
- pyproject.toml (gestor uv, Python >=3.12,<3.13). Dependencias: simpy>=4, numpy, pydantic>=2,
  fastapi, uvicorn[standard], jinja2, sqlalchemy>=2, alembic, psycopg[binary]>=3, openai>=1,
  httpx, pydantic-settings. Dev: pytest, pytest-asyncio, ruff, honcho.
  Configura ruff (line-length 100, reglas E,F,I,UP,B) y pytest (testpaths=tests, asyncio_mode=auto).
  Empaquetado: que los paquetes de arriba sean importables (setuptools packages.find o equivalente).
- .python-version con 3.12.
- config.py en la raíz con una clase Settings (pydantic-settings, lee .env) con: DATABASE_URL, MODE
  (live|replay, default live), LLM_BASE_URL, LLM_MODEL, LLM_API_KEY, ADMIN_TOKEN, SIM_WORKERS.
  Normaliza DATABASE_URL: si empieza con postgresql:// o postgres:// (formato de Railway), la
  convierte a postgresql+psycopg:// y conserva parámetros como sslmode.
- .env.example con esas variables y valores de desarrollo local nativo:
  DATABASE_URL=postgresql+psycopg://planta:planta@localhost:5432/planta,
  LLM_BASE_URL=http://localhost:8001/v1, LLM_MODEL=mock, LLM_API_KEY=mock, MODE=live.
  Agrega .env a .gitignore.
- El repo ya trae LICENSE (MIT), README.md y .gitignore de Python creados por GitHub: no los
  reemplaces; agrega .env y .venv al .gitignore y amplía el README a unas 10 líneas.
- tests/test_smoke.py que importe cada paquete, y un test de la normalización de DATABASE_URL.

El desarrollo es nativo en Linux (sin Docker). No crees Dockerfile ni docker-compose.yml:
el Dockerfile para Railway llega en el Prompt 6 y docker compose no se usa en este proyecto.

No hagas: lógica del simulador, esquema de política, modelos de BD, Makefile, Dockerfile, CI
(van en prompts siguientes). No agregues dependencias que no estén en la lista.

Aceptación:
- `uv sync` funciona y genera uv.lock.
- `uv run pytest -q` pasa y `uv run ruff check .` sale limpio.
Muéstrame el árbol final de carpetas.

Caja de tiempo: 30 min.
```

---

## Prompt 1: esquema Pydantic de la política

**Hora:** 14:00 a 14:45 (45 min) · **OBLIGATORIO HOY**

```text
Objetivo: implementar policy/schema.py, el contrato de la política (sección 5.3 de docs/PLAN.md).

Especificación (Pydantic v2, model_config extra="forbid" en todos los modelos):
- Constantes: MACHINES = M1..M5, PRODUCTS = P1..P3.
- Maintenance: pm_wear_threshold: dict[MachineId, float] (rango 0.30 a 0.95; las máquinas
  ausentes usan DEFAULT_PM_THRESHOLD = 0.75), max_pm_per_shift: int (0 a 3).
- Dispatch: rule: Literal["EDD","SPT","WEIGHTED","CRITICAL_RATIO"];
  weights: {due_date, wear_risk, setup} cada uno en [0,1]. Si la suma es 0, error; si no, se
  normalizan a suma 1 en un model_validator. weights es obligatorio solo si rule == "WEIGHTED"
  o "CRITICAL_RATIO"; si falta en los demás casos se usa un default.
- Condition (todos opcionales, al menos uno presente): machine (MachineId), wear_gt (0.50 a 0.99),
  urgent_order_waiting (bool), queue_len_gt (int 1 a 50), product_waiting (ProductId).
- Action como unión discriminada por "action":
  POSTPONE_PM (max_minutes int 15 a 240), FORCE_PM (machine opcional),
  BATCH_SAME_PRODUCT (sin parámetros), PRIORITIZE_PRODUCT (product obligatorio).
- Rule: campos con alias "if" y "then" (en Python: cond y then_; populate_by_name=True,
  serializar por alias).
- Policy: maintenance, dispatch, rules: list[Rule] con máximo 5. Agrega un version: int = 1.
- Funciones: parse_policy(raw: dict | str) -> Policy, policy_json_schema() -> dict (para la
  decodificación guiada de vLLM más adelante), fixed_rule_policy() -> Policy (la "regla fija":
  EDD, umbral 0.75 en todas, max_pm_per_shift 1, sin reglas).
- Guarda el JSON de ejemplo del plan en policy/examples/example_v2.json y fixed_rule.json.

Tests (tests/test_policy_schema.py):
- El ejemplo del plan valida y hace round-trip (dump por alias -> parse -> igual).
- Se rechazan: 6 reglas, umbral 0.99 en maintenance, máquina "M9", producto "P4", acción
  desconocida, campo extra, POSTPONE_PM sin max_minutes, condición vacía, pesos todos en 0.
- Los pesos se normalizan a suma 1.
- policy_json_schema() es serializable a JSON y menciona las 4 reglas de despacho.

No hagas: lógica de simulación ni interpretación de las reglas (eso es el Prompt 2).

Aceptación: `uv run pytest tests/test_policy_schema.py -q` pasa; ruff limpio.
```

---

## Prompt 2: simulador v0 (modelo de planta)

**Hora:** 14:45 a 16:15 (90 min) · **OBLIGATORIO HOY**

```text
Objetivo: simulador SimPy v0 en sim/ (sección 5.1 de docs/PLAN.md). Usa policy/schema.py.

Archivos: sim/config.py, sim/model.py (Plant, Machine, Order), sim/failures.py, sim/dispatch.py,
sim/rules.py. Todos los parámetros en un dataclass frozen PlantConfig con defaults.

Modelo (unidades en minutos):
- Línea en serie M1 a M5; cada orden pasa por las 5 máquinas. Horizonte 7 días, turnos de 8 h.
- 3 productos P1..P3 con tiempo de proceso por máquina (lognormal alrededor de una media por
  producto y máquina) y setup al cambiar de producto en una máquina.
- Órdenes: llegadas Poisson, producto aleatorio con mezcla configurable, cantidad 1, due date =
  llegada + holgura aleatoria; urgent=True si la holgura restante es menor que un umbral.
- Desgaste: cada minuto de proceso suma wear según producto y máquina; wear en [0,1].
- 3 modos de falla (MECANICA, ELECTRICA, HERRAMIENTA): riesgo por minuto que crece con wear
  (función logística o Weibull, en sim/failures.py, parámetros en PlantConfig para calibrar
  después). Falla = paro no planificado con duración aleatoria por modo, costo de reparación,
  wear vuelve a 0.
- Mantenimiento preventivo (PM): se dispara cuando wear >= umbral de la política, respetando
  max_pm_per_shift; duración y costo fijos menores que una falla; wear vuelve a 0.
- Despacho por cola de cada máquina: EDD, SPT, WEIGHTED (score con weights), CRITICAL_RATIO.
- Reglas condicionales: se evalúan en cada decisión de despacho y de PM, en orden; la primera
  que aplique gana. POSTPONE_PM retrasa el PM hasta max_minutes; FORCE_PM lo adelanta;
  BATCH_SAME_PRODUCT prefiere el mismo producto que el último; PRIORITIZE_PRODUCT lo prioriza.

Determinismo: un único seed crea un numpy SeedSequence y de ahí streams separados para
llegadas, tiempos de proceso, fallas y reparaciones (números aleatorios comunes: cambiar la
política no debe alterar la secuencia de llegadas). Nada de random global ni reloj real.

No hagas: KPIs ni simulate() todavía (Prompt 3), paralelismo, calibración real, UI, logging
pesado. Prioriza velocidad: nada de pandas dentro del bucle.

Aceptación: tests/test_sim_model.py con una corrida corta (1 día) que termina, procesa
órdenes y nunca deja wear fuera de [0,1]. pytest y ruff limpios.
```

---

## Prompt 3: simulate(), KPIs, objetivo y benchmark

**Hora:** 16:15 a 17:15 (60 min) · **OBLIGATORIO HOY**

```text
Objetivo: función pura de simulación con métricas, objetivo compuesto y benchmark de velocidad.

Archivos: sim/runner.py, sim/kpis.py, sim/objective.py, sim/calibration.py (stub),
bench/sim_speed.py, tests/test_sim_runner.py.

Especificación:
- simulate(policy: Policy | dict, seed: int, config: PlantConfig | None = None,
  scenario: Literal["base","stress"] = "base") -> dict[str, float].
  Pura: sin red, disco ni BD; argumentos y retorno picklables (apta para ProcessPoolExecutor).
  "stress" = tasa de fallas +30% y pico de demanda (como en el plan, sección 6).
- KPIs devueltos: throughput (órdenes terminadas), on_time_rate (0 a 1), unplanned_downtime_h,
  planned_downtime_h, maintenance_cost, orders_created, orders_completed, orders_wip,
  failures_total, failures_by_mode_* , pm_count, sim_wall_s (tiempo real de la corrida, que
  NO entra en ninguna comparación de determinismo).
- sim/objective.py: ObjectiveWeights (pydantic, editables, defaults en un JSON
  sim/objective_weights.json) y composite_objective(metrics, weights) -> float, mayor es
  mejor; normaliza cada KPI por una escala de referencia para que los pesos sean comparables.
- simulate_many(policy, seeds, workers) usando ProcessPoolExecutor; devuelve lista de métricas.
- sim/calibration.py: stub con la firma fit_failure_curve(dataset_path) -> FailureParams que
  hoy devuelve los defaults y un docstring que explica que se calibrará con AI4I 2020 o C-MAPSS.

Tests:
- Misma semilla y misma política => métricas idénticas (excluyendo sim_wall_s).
- Semillas distintas => métricas distintas.
- Conservación: orders_created == orders_completed + orders_wip.
- simulate_many con 2 workers da lo mismo que en serie.
- stress produce más fallas en promedio que base (10 semillas).
- Una política inválida (dict) lanza ValidationError antes de simular.

bench/sim_speed.py: `uv run python -m bench.sim_speed --seeds 50 --workers N` imprime
segundos por simulación (media y p95) en serie y en paralelo, y cuántas simulaciones
caben en 25 min para K=100, N=32, R=8 (25,600 sims).

No hagas: búsqueda, Optuna, calibración real, gráficas.

Aceptación: pytest y ruff limpios; el benchmark corre e imprime los números.
```

---

## Prompt 4: cliente LLM y mock compatible con OpenAI

**Hora:** 17:15 a 18:15 (60 min) · **OBLIGATORIO HOY**

```text
Objetivo: llm/client.py que hable con cualquier endpoint compatible con OpenAI, y un servidor
mock que devuelve políticas válidas. Cambiar a vLLM real debe ser solo cambiar LLM_BASE_URL y
LLM_MODEL.

Archivos: llm/client.py, llm/prompts.py, llm/mock_server.py, tests/test_llm_client.py.

Especificación:
- llm/mock_server.py: app FastAPI con POST /v1/chat/completions y GET /v1/models. Responde
  con el formato de OpenAI (choices[].message.content, usage con tokens). El content es un
  JSON de Policy válido generado con un Generator sembrado con el campo "seed" del request
  (o un hash del prompt si no viene). Varía regla de despacho, umbrales y 0 a 5 reglas.
  Parámetro de entorno MOCK_INVALID_RATE (default 0) para devolver a veces JSON inválido.
  Se ejecuta nativo con `uv run uvicorn llm.mock_server:app --host 127.0.0.1 --port 8001`
  (el Makefile del Prompt 6 lo envolverá como `make mock-llm`).
- llm/client.py: clase LLMClient(base_url, model, api_key, concurrency=32) con AsyncOpenAI.
  - async propose(context: str, n: int, seed: int) -> ProposeResult: lanza n peticiones en
    paralelo con un asyncio.Semaphore, pasa response_format/extra_body con el JSON Schema de
    policy_json_schema() (guided decoding de vLLM; el mock lo ignora), valida cada respuesta
    con parse_policy y devuelve válidas, inválidas (con el error), latencias y tokens/seg.
  - async explain(metrics: dict) -> str: devuelve texto (en el mock, una plantilla que usa
    solo números del dict).
  - from_settings() que lea LLM_BASE_URL, LLM_MODEL, LLM_API_KEY de config.py.
- llm/prompts.py: plantillas de texto para proponer y explicar (sin lógica de búsqueda).

Tests (sin red: inyecta httpx.AsyncClient(transport=httpx.ASGITransport(app=mock_app))
en AsyncOpenAI):
- propose(n=8) devuelve 8 políticas válidas y métricas de latencia.
- Con MOCK_INVALID_RATE=0.5 algunas quedan en inválidas y no rompen nada.
- Misma seed => mismas políticas.

No hagas: llamar a vLLM real, bucle de búsqueda, tarjeta de operador con guard (martes en
adelante), reintentos complejos.

Aceptación: pytest y ruff limpios (los tests no levantan ningún servidor); con el mock
levantado en otra terminal, `uv run python -m llm.client --n 4` (usa LLM_BASE_URL de .env,
http://localhost:8001/v1) imprime 4 políticas válidas.
```

---

## Prompt 5: base de datos, API mínima y worker stub

**Hora:** 18:30 a 19:30 (60 min, después de 15 min de pausa) · **OBLIGATORIO HOY**

```text
Objetivo: persistencia con SQLAlchemy 2 + Alembic, API FastAPI mínima y un worker que reclama
trabajos de Postgres.

Archivos: db/models.py, db/session.py, alembic.ini, db/migrations/ (Alembic), api/main.py,
worker/main.py, ui/templates/index.html, tests/test_db.py, tests/test_api.py.

Modelos (SQLAlchemy 2, Mapped/mapped_column, timestamps con timezone):
- jobs: id (uuid), kind (search|baseline|eval), status (queued|running|done|failed),
  params (JSONB), created_at, started_at, finished_at, error.
- policies: id, job_id (FK), round, source (fixed|llm|optuna|llm_no_feedback),
  policy_json (JSONB), valid (bool), approved_at (nullable).
- metrics: id, policy_id (FK), seed_set (train|holdout|stress), n_seeds, objective,
  kpis (JSONB con medias), ci_low, ci_high, sims_spent.
- runs: id, job_id (FK), seq, event_type, payload (JSONB), created_at. Es el log completo
  que usará el modo replay.
Migración inicial con `alembic revision --autogenerate`, revisada a mano.

API (api/main.py): GET /healthz (200 siempre, {"status":"ok"}), GET /readyz (hace SELECT 1;
200 o 503), GET / que renderiza ui/templates/index.html: placeholder con el nombre del
proyecto, el MODE actual y un texto "UI en construcción". Nada más.

Worker (worker/main.py): bucle que reclama un job queued con SELECT ... FOR UPDATE SKIP
LOCKED, lo marca running, y para kind=baseline simula fixed_rule_policy() en 10 semillas,
guarda policy + metrics + eventos en runs y marca done (o failed con el error).
Expón process_one(session) -> bool para testear. Script `python -m worker.enqueue baseline`.

Tests: los de BD se marcan @pytest.mark.db y se saltan si no hay DATABASE_URL o la BD no
responde. Usan el Postgres nativo de .env en local y el de services: en CI. Cubren:
migración aplica, enqueue + process_one deja el job en done con métricas guardadas, dos
process_one concurrentes no toman el mismo job. test_api usa TestClient: healthz 200,
readyz 503 sin BD.

No hagas: POST /jobs, aprobación, autenticación, HTMX, gráficas, SSE.

Aceptación: con el Postgres nativo (base planta creada), `uv run alembic upgrade head`
funciona y pytest pasa completo; sin BD, pytest pasa saltando los tests db. En otra
terminal, `uv run python -m worker.main` procesa un job creado con
`uv run python -m worker.enqueue baseline`.

No hagas: nada con Docker ni docker compose.
```

---

## Prompt 6: Makefile nativo, CI y Dockerfile solo para Railway

**Hora:** 19:30 a 20:15 (45 min) · **OBLIGATORIO HOY**

```text
Objetivo: correr todo en local de forma nativa con un Makefile (sin Docker), CI en GitHub
Actions con Postgres como service, y dejar Dockerfile + railway.toml listos solo para el
despliegue (sin desplegar).

Archivos: Makefile, Procfile.dev, .github/workflows/ci.yml, Dockerfile, .dockerignore,
railway.toml, README.md (sección "Correr en local").

Makefile (nativo, carga .env; asume Postgres ya instalado y el rol planta creado):
- setup: uv sync.
- db: crea la base si no existe con createdb (deriva host, usuario, puerto y nombre de
  DATABASE_URL quitando el "+psycopg"; si ya existe, no falla) y luego
  uv run alembic upgrade head.
- mock-llm: uv run uvicorn llm.mock_server:app --host 127.0.0.1 --port 8001.
- web: uv run uvicorn api.main:app --reload --port 8000.
- worker: uv run python -m worker.main.
- dev: uv run honcho start -f Procfile.dev (mock-llm, web y worker juntos, logs con prefijo).
- test: uv run pytest -q. lint: uv run ruff check . && uv run ruff format --check .
- bench: uv run python -m bench.sim_speed --seeds 50.
- enqueue-baseline: uv run python -m worker.enqueue baseline.
- docker-build (opcional): docker build -t planta . (solo para verificar la imagen de Railway).
Procfile.dev con las tres líneas (mock, web, worker) usando los mismos comandos.

CI (.github/workflows/ci.yml), en push y pull_request:
- Job lint: setup de uv, uv sync, ruff check y ruff format --check.
- Job test: services: postgres (imagen postgres con la misma versión mayor que Railway; déjala
  en una variable PG_MAJOR al inicio del workflow con un comentario "igualar a Railway"),
  healthcheck con pg_isready, DATABASE_URL apuntando a localhost:5432, alembic upgrade head,
  pytest -q (incluye tests db). Cache de uv. Esto no depende del entorno local.
- Job docker: docker build (sin push), para verificar que la imagen de Railway compila.

Dockerfile (solo para Railway, no se usa para desarrollar):
- python:3.12-slim + uv, uv sync --frozen --no-dev, usuario no root, sin copiar .env.
- Una sola imagen para web y worker: el comando por defecto arranca web
  (alembic upgrade head y luego uvicorn api.main:app --host 0.0.0.0 --port $PORT);
  worker = python -m worker.main como comando alternativo.
.dockerignore: .env, .venv, .git, __pycache__, tests de caché.

railway.toml: builder DOCKERFILE, startCommand de web, healthcheckPath = "/healthz",
healthcheckTimeout razonable, restartPolicyType = "ON_FAILURE". En comentarios: DATABASE_URL
se define en Railway como referencia al servicio Postgres (${{Postgres.DATABASE_URL}}).

README, sección "Correr en local": requisitos (Python 3.12, uv, Postgres con la misma versión
mayor que Railway), crear el rol una vez, cp .env.example .env, make setup, make db, make dev.

No hagas: docker-compose.yml ni ningún uso de Docker para desarrollo o tests; despliegue a
Railway; push de imágenes; secretos en el workflow; vLLM; up.sh de la GPU (eso es el Prompt 8).

Aceptación:
- `cp .env.example .env && make setup && make db` deja la base migrada.
- Con `make dev` arriba, `curl localhost:8000/healthz` y `curl localhost:8000/readyz`
  devuelven 200, y `make enqueue-baseline` hace que el worker deje el job en done (se ve en
  los logs de honcho).
- `make test` y `make lint` pasan.
- El workflow pasa al hacer push a GitHub (incluido el job docker). Antes de cerrar este
  prompt, haz push y confirma el check verde en la pestaña Actions.
- `make docker-build` local es opcional hoy; puede quedar para el viernes, día del deploy.
```

---

## Prompt 7: cierre de la línea base

**Hora:** 20:15 a 20:45 (30 min) · **OBLIGATORIO HOY**

```text
Objetivo: verificar todo, medir la velocidad real en esta máquina y dejar el repo listo para la
primera sesión de GPU del martes.

Haz, en este orden, y reporta la salida real de cada paso:
1. `make lint` y `make test` (con el Postgres nativo arriba para incluir los tests db).
2. Base limpia: `dropdb -h localhost -U planta planta && make db`. Luego `make dev`;
   comprueba /healthz, /readyz, la página / y un job baseline de punta a punta
   (`make enqueue-baseline`).
3. `uv run python -m bench.sim_speed --seeds 100 --workers <núcleos de esta máquina>`.
   Anota: segundos por simulación (media y p95), en serie y en paralelo, núcleos usados y CPU.
4. Con esos números, estima cuánto tardarían 25,600 simulaciones aquí y cuántos núcleos
   harían falta para bajar de 25 min. Escríbelo en docs/BENCHMARKS.md con fecha y hardware.
5. README.md: qué es (3 líneas), requisitos (Python 3.12, uv, Postgres nativo), crear el rol,
   `cp .env.example .env`, `make setup`, `make db`, `make dev`, cómo correr tests y benchmark,
   variables de entorno, cómo apuntar a un vLLM propio (solo cambiar LLM_BASE_URL, LLM_MODEL,
   LLM_API_KEY), nota de que Docker solo se usa para la imagen de Railway, licencia MIT, aviso
   de que es una planta simulada y de que todo el código se escribió durante el hackathon,
   a partir del lunes 12 de octubre de 2026 después del kickoff.
6. docs/PENDIENTES_MARTES.md con lo que falta, en orden: lo que no se terminó hoy (sé honesto,
   incluye los prompts 8 a 10 si quedaron pendientes), confirmar precio por hora en la consola,
   crear la instancia MI300X y up.sh, vLLM con 2 modelos y salida JSON guiada, smoke y
   benchmarks reales, fijar K y N, destruir la instancia, arrancar el bucle de búsqueda,
   revisar la versión mayor del Postgres de Railway e igualarla en local y en PG_MAJOR del CI.
7. Revisa que no haya secretos ni .env en git (`git status`, `git ls-files | grep -i env`).

No hagas: código nuevo de funcionalidades. Solo arreglos necesarios para que todo pase.

Termina con un resumen de 10 líneas: qué funciona, números del benchmark, qué falta.
```

---

## Prompt 8: scripts de la instancia (sin GPU)

**Hora:** 20:45 a 21:15 (30 min) · **PUEDE PASAR AL MARTES EN LA MAÑANA**

```text
Objetivo: dejar en infra/gpu/ los scripts para levantar y apagar una sesión de trabajo en la
instancia MI300X de AMD Developer Cloud (sección 8 "GPU" de docs/PLAN.md). Hoy no se ejecutan
contra la GPU; solo deben ser correctos, idempotentes y pasar shellcheck.

Archivos: infra/gpu/up.sh, infra/gpu/vllm.sh, infra/gpu/worker.sh, infra/gpu/README.md,
infra/gpu/.env.gpu.example.

up.sh (se ejecuta en la instancia recién creada, como usuario con sudo):
- set -euo pipefail. Imprime rocm-smi (o amd-smi) y nproc al inicio para confirmar el hardware.
- Instala uv si falta, clona el repo (URL por variable REPO_URL) o hace git pull si ya existe,
  y corre uv sync.
- Instala tmux si falta. No instala Postgres (el worker usa el de Railway; el plan B local es manual).
- No arranca nada por sí solo: al final imprime los siguientes comandos a ejecutar.

vllm.sh:
- Variables con defaults en .env.gpu: VLLM_IMAGE (default rocm/vllm:latest, con un comentario que
  diga "fijar el tag exacto que funcione hoy"), MODEL, VLLM_API_KEY (obligatoria, falla si está vacía),
  MAX_MODEL_LEN, GPU_MEM_UTIL (default 0.90), HF_TOKEN opcional, HF_HOME en un volumen persistente.
- docker run -d --name vllm con --device=/dev/kfd --device=/dev/dri --group-add video --ipc=host
  --security-opt seccomp=unconfined --network=host, y el comando
  vllm serve "$MODEL" --host 127.0.0.1 --port 8000 --api-key "$VLLM_API_KEY"
  --max-model-len "$MAX_MODEL_LEN" --gpu-memory-utilization "$GPU_MEM_UTIL".
  Escucha solo en 127.0.0.1: nunca 0.0.0.0.
- Espera a que GET /v1/models responda (timeout configurable, muestra docker logs si falla).
- Subcomandos: start, stop, logs, status.

worker.sh: arranca `uv run python -m worker.main` dentro de una sesión tmux llamada worker,
cargando .env.gpu (DATABASE_URL pública de Railway con sslmode=require, LLM_BASE_URL
http://127.0.0.1:8000/v1, LLM_MODEL, LLM_API_KEY = VLLM_API_KEY, SIM_WORKERS = nproc - 2).

infra/gpu/README.md, en este orden:
1. Crear la instancia en la consola (anotar precio por hora y hora de inicio).
2. ssh, copiar .env.gpu (nunca al repo), ./up.sh, ./vllm.sh start.
3. Túnel desde tu Linux: ssh -N -L 8000:127.0.0.1:8000 usuario@IP, para usar vLLM en local.
4. Benchmarks del Prompt 10.
5. Checklist de cierre: copiar resultados (scp de docs/BENCHMARKS.md o git push), ./vllm.sh stop,
   y DESTRUIR la instancia en la consola (apagarla no basta: puede seguir cobrando). Anotar hora de
   fin y costo estimado.

Agrega .env.gpu a .gitignore. Agrega un job o paso de CI que corra shellcheck sobre infra/gpu/*.sh.

No hagas: Terraform, llamadas a la API de DigitalOcean, exponer puertos, Caddy (solo si un día
hiciera falta exponer vLLM), cambios en sim/ o policy/.

Aceptación: shellcheck limpio, bash -n en cada script, make test y make lint pasan.
```

---

## Prompt 9: smoke test del LLM con JSON guiado (contra el mock)

**Hora:** 21:15 a 21:40 (25 min) · **PUEDE PASAR AL MARTES EN LA MAÑANA**

```text
Objetivo: un script que verifique, contra cualquier endpoint compatible con OpenAI, que el modelo
devuelve políticas válidas usando el esquema de policy_json_schema(). Debe funcionar igual contra
el mock (local) y contra vLLM (por el túnel SSH), cambiando solo LLM_BASE_URL, LLM_MODEL y LLM_API_KEY.

Archivo: bench/llm_smoke.py (uv run python -m bench.llm_smoke --n 8).

Especificación:
- Usa LLMClient de llm/client.py (no un cliente nuevo).
- Revisa que la forma de pedir salida estructurada sea la que acepta el vLLM actual del servidor
  OpenAI: response_format={"type":"json_schema","json_schema":{"name":"policy","schema":...,
  "strict":true}}. Si LLMClient usa otra forma (por ejemplo guided_json en extra_body), cámbiala a
  esta o agrega un flag --structured-mode {response_format,extra_body} y documenta cuál funcionó.
- Imprime: modelo reportado por /v1/models, n pedidas, válidas, inválidas con el primer error,
  latencia p50 y p95, tokens de salida por segundo agregados, y una política de ejemplo.
- Código de salida distinto de 0 si la tasa de válidas es menor que 0.95.
- Si el modelo genera razonamiento antes del JSON (modelos con "thinking"), detecta el caso y
  avisa en la salida: para este proyecto conviene desactivar el razonamiento o usar un modelo sin él.

Tests: test que corre el smoke contra el mock con httpx.ASGITransport (sin red) y verifica el
formato de la salida.

No hagas: bucle de búsqueda, prompts nuevos de negocio, reintentos complejos.

Hoy solo contra el mock; contra vLLM real se corre el martes por el túnel SSH.

Aceptación: contra `make mock-llm` imprime 8/8 válidas; pytest y ruff limpios.
```

---

## Prompt 10: harness de benchmarks para fijar K y N (contra el mock)

**Hora:** 21:40 a 22:00 (20 min) · **PUEDE PASAR AL MARTES EN LA MAÑANA**

```text
Objetivo: medir en la instancia lo que define el tamaño de la búsqueda, y dejar K, N y R como
configuración, no como números sueltos en el código.

Archivos: bench/llm_throughput.py, bench/budget.py, search/config.py, docs/BENCHMARKS.md (secciones
"Lunes 12, máquina local" y "Martes 13, MI300X").

bench/llm_throughput.py (uv run python -m bench.llm_throughput --concurrency 8,16,32,64 --n 64):
- Para cada nivel de concurrencia: políticas válidas por minuto, tokens de salida por segundo,
  latencia p50 y p95 de una propuesta, tasa de válidas. Salida como tabla y como JSON en
  bench/results/llm_<modelo>_<fecha>.json.

bench/budget.py:
- Lee el último JSON de llm_throughput y el de sim_speed (agrega salida JSON a bench/sim_speed.py
  si no la tiene) y calcula, para combinaciones de N (16, 32, 48), K (30, 50, 100) y R (6, 8),
  cuánto tarda una búsqueda completa (tiempo de LLM + tiempo de simulación con SIM_WORKERS) más
  300 semillas reservadas y el escenario de estrés.
- Recomienda la combinación más grande que quepa en SEARCH_TARGET_MIN (default 25 min) e imprime
  también el costo estimado en dólares con GPU_PRICE_PER_HOUR (variable, sin default inventado).

search/config.py: SearchConfig (pydantic-settings) con N, K, R, TOP_K, HOLDOUT_SEEDS=300,
SEARCH_TARGET_MIN; defaults iguales al plan (N=32, K=100, R=8) hasta que el benchmark diga otra cosa.

docs/BENCHMARKS.md: deja la plantilla con huecos para modelo, imagen de vLLM (tag exacto), núcleos,
precio por hora, resultados y la combinación elegida. No inventes números: se llenan con la corrida real.

No hagas: el bucle de búsqueda (es el martes en la tarde), Optuna.

Hoy solo se corre contra el mock; los números reales se miden el martes en la MI300X.

Aceptación: contra el mock, llm_throughput y budget corren de punta a punta y producen la tabla;
pytest y ruff limpios.
```

---

## Checklist de cierre (lunes, ~22:00)

- [ ] Repo público `twinverdict` en GitHub, MIT, creado hoy después del kickoff; un commit por prompt con push.
- [ ] `docs/PLAN.md` (v4) y archivo de contexto en el repo.
- [ ] `policy/schema.py` valida el ejemplo y rechaza más de 5 reglas, umbrales fuera de rango y campos extra.
- [ ] `simulate(policy, seed)` pura, determinista y conserva órdenes; KPIs y objetivo con pesos editables; escenario `stress`; `simulate_many`.
- [ ] Mock LLM y `LLMClient`; cambiar a vLLM = cambiar `LLM_BASE_URL` y `LLM_MODEL`.
- [ ] Postgres nativo con Alembic (jobs, policies, metrics, runs); worker con `SKIP LOCKED` y job baseline en done.
- [ ] `make setup`, `make db`, `make dev` funcionan; `/healthz` y `/readyz` en 200.
- [ ] Sin `docker-compose.yml`. `Dockerfile` y `railway.toml` solo para Railway.
- [ ] CI en verde en GitHub (lint, tests con Postgres como `services:`, `docker build`).
- [ ] `docs/BENCHMARKS.md` con segundos por simulación en tu máquina y `docs/PENDIENTES_MARTES.md`.
- [ ] Sin `.env` ni claves en git.
- [ ] Método de pago agregado en DigitalOcean. Cero gasto de GPU (salvo que todo lo anterior esté listo y el precio confirmado).
- [ ] Si se hicieron: `infra/gpu/` con shellcheck en CI; `bench.llm_smoke` 8/8 contra el mock; `bench.llm_throughput` y `bench.budget` corren contra el mock.

## Qué queda para el martes

1. **Mañana, sin GPU:** terminar lo que se deslizó (Prompts 8 a 10 si no se hicieron).
2. **Confirmar el precio por hora de la MI300X en la consola** ($1.99 o $2.59) y elegir la tabla de 50 h o 38 h del plan v4.
3. **Primera sesión de GPU** (manual, con el reloj corriendo):
   1. Crear la instancia; anotar hora de inicio y precio.
   2. `scp` de `.env.gpu`, `./infra/gpu/up.sh`, `./infra/gpu/vllm.sh start` con el modelo A.
   3. Túnel SSH (`ssh -N -L 8000:127.0.0.1:8000 usuario@IP`) y `uv run python -m bench.llm_smoke --n 32`; si pasa, `bench.llm_throughput`.
   4. Repetir con el modelo B; elegir por tasa de válidas, estabilidad y políticas por minuto, en ese orden.
   5. En la instancia: `bench.sim_speed --workers <nproc - 2>` y `bench.budget` con `GPU_PRICE_PER_HOUR`.
   6. Fijar N, K y R en `search/config.py`, llenar `docs/BENCHMARKS.md`, commit y push.
   7. `./infra/gpu/vllm.sh stop` y **destruir la instancia** (no solo apagarla). Anotar hora de fin y costo.
4. **Tarde y noche:** bucle de búsqueda (primero en local contra el mock, luego en la instancia). Hito: una búsqueda de punta a punta guardada en Postgres. Si a la noche no corre, corte 2: 3 máquinas y R=6.
5. Preguntar en el Discord de lablab: si replay + video bastan para el componente AMD, y qué tecnología de Google cuenta para el premio de $5,000 (no agregar nada de Google hasta el jueves).
