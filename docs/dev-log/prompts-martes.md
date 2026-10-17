# TwinVerdict: prompts del martes 13 oct (mañana GPU + tarde bucle)

Plan de referencia: `docs/PLAN.md` (fila "Mar 13") y `docs/PENDIENTES_MARTES.md` en el repo.

**Estado al arrancar (verificado en GitHub `focampok/twinverdict`, commits del lun 12):** prompts 0 a 10 hechos; `infra/gpu/` listo; smoke y harness contra el mock; precio anotado $2.59/h bajo demanda (tabla B ~38 h); método de pago ya en la cuenta. No hace falta el catch-up de 8 a 10.

**Objetivo de hoy:** (1) primera sesión de GPU: crear instancia, vLLM con 2 modelos, elegir el estable, smoke JSON, benchmarks, fijar K y N, destruir la instancia, (2) tarde/noche: bucle de búsqueda primero contra el mock y luego en la instancia si cabe. **Hito:** una búsqueda de punta a punta guardada en Postgres.

**Regla de oro:** el código se escribe y se prueba en local contra el mock. La GPU solo mide, elige modelo y graba. Cada sesión arranca con lista escrita de qué medir y termina **destruyendo** la instancia (apagarla puede seguir cobrando). Tope de montaje hoy: ~4 h (escenario B).

## Agenda del día

| Hora (GT) | Paso | Prioridad |
|---|---|---|
| 08:30 a 09:00 | Paso 0 manual: confirmar precio en consola, elegir 2 modelos, copiar `.env.gpu` | Obligatorio |
| 09:00 a 09:30 | Prompt 11: `docs/SESION_GPU.md` (ritual escrito antes de crear) | Obligatorio |
| 09:30 a ~13:30 | Sesión GPU 1 (manual, reloj corriendo; tope ~4 h) | Obligatorio |
| 13:30 a 14:00 | Cierre post-GPU: BENCHMARKS, N/K/R, commit, confirmar destrucción | Obligatorio |
| 14:00 a 16:30 | Prompt 12: bucle de búsqueda (`search/loop.py`) contra el mock | Obligatorio |
| 16:30 a 18:00 | Prompt 13: persistir corrida completa en Postgres (`runs`) | Obligatorio |
| 18:00 a 19:30 | Prompt 14: worker ejecuta un job de búsqueda de punta a punta | Obligatorio |
| 19:30 a 21:30 | Sesión GPU 2 (opcional): una búsqueda real con el modelo ya elegido | Si el hito mock ya pasó |
| 21:30 a 22:00 | Checklist de cierre y `docs/PENDIENTES_MIERCOLES.md` | Obligatorio |

Si a la noche el bucle no corre de punta a punta, corte 2 del plan: 3 máquinas y R=6.

## Paso 0 manual (08:30 a 09:00)

1. En la consola de AMD Developer Cloud / DigitalOcean, confirma que la MI300X muestra **$2.59/h** (o anota el número real si cambió). Escenario B del plan: ~38 h con $100.
2. Elige **dos modelos** abiertos que la imagen ROCm del día pueda servir; prioriza salida JSON sin "thinking" largo. Anótalos como A y B (ids exactos de HF).
3. Prepara `.env.gpu` desde `infra/gpu/.env.gpu.example` (nunca al repo): `VLLM_API_KEY`, `MODEL`, `REPO_URL`, y deja `DATABASE_URL` de Railway pública para más tarde (`sslmode=require`).
4. Actualiza el archivo de contexto con el bloque "Alcance actual (martes 13)" de abajo (o espera al Prompt 11).
5. Preguntas para Discord de lablab (cualquier hueco del día; no bloquean la GPU):
   - ¿Basta replay de una corrida real en la MI300X más el video para el componente AMD?
   - ¿Qué tecnología de Google cuenta para el premio de $5,000? (Nada de Google hasta el jueves.)
   - ¿Restricciones de modelos o tamaños?
6. Anota aparte: local y CI están en Postgres 16; igualar la versión mayor de Railway cuando toque (punto 9 de `PENDIENTES_MARTES.md`).

### Alcance actual (pegar en el archivo de contexto)

```markdown
## Alcance actual (martes 13)
Primera sesión de GPU: instancia MI300X ($2.59/h, destruir al terminar), vLLM ROCm en
127.0.0.1 con --api-key, probar 2 modelos, elegir el estable, smoke JSON, benchmarks,
fijar N/K/R. Tarde: bucle de búsqueda (proponer, validar, simular, guardar) primero contra
el mock; hito una corrida completa en Postgres. Si cabe, una búsqueda real en la instancia.
No implementar: Optuna, UI completa, Railway en producción, SSE, premio de Google, docker compose.
```

## Cómo usar los prompts

Uno por uno, revisar diff, `make test` y `make lint`, commit por prompt (`git commit -m "prompt 12: search loop"`) y push. No reescribas historia ya subida.

---

## Prompt 11: checklist de sesión GPU en el repo

**Hora:** 09:00 a 09:30 (30 min) · **OBLIGATORIO HOY**

```text
Objetivo: dejar escrito en el repo el ritual de una sesión de GPU para no improvisar con
el reloj corriendo. No crear la instancia todavía.

Archivos: docs/SESION_GPU.md (checklist numerada), y asegúrate de que docs/BENCHMARKS.md
tenga la plantilla "Martes 13, MI300X" con huecos (ya existe; no inventes números).

docs/SESION_GPU.md, en este orden:
1. Anotar precio/hora mostrado en la consola, hora de inicio, escenario B (~38 h a $2.59).
2. Crear instancia con imagen ROCm; anotar IP y usuario SSH.
3. scp de .env.gpu (nunca al repo); ./infra/gpu/up.sh; ./infra/gpu/vllm.sh start con MODEL=A.
4. Túnel desde Linux: ssh -N -L 8000:127.0.0.1:8000 usuario@IP.
5. uv run python -m bench.llm_smoke --n 32; si tasa de válidas < 0.95, logs y ajuste o modelo B.
6. uv run python -m bench.llm_throughput --concurrency 8,16,32,64 --n 64.
7. Repetir 5-6 con modelo B; elegir por (1) tasa de válidas, (2) estabilidad del contenedor,
   (3) políticas por minuto.
8. En la instancia: uv run python -m bench.sim_speed --seeds 100 --workers $(($(nproc)-2)).
9. GPU_PRICE_PER_HOUR=2.59 uv run python -m bench.budget; fijar N,K,R en search/config.py.
10. Llenar docs/BENCHMARKS.md sección "Martes 13, MI300X" con números reales; commit y push.
11. ./infra/gpu/vllm.sh stop; DESTRUIR la instancia en la consola; anotar hora de fin y costo.

Actualiza el bloque "Alcance actual" del archivo de contexto al texto del martes 13.

No hagas: Terraform, API de DigitalOcean, bucle de búsqueda, Optuna, UI, exponer vLLM a 0.0.0.0.

Aceptación: docs/SESION_GPU.md completo; make test y make lint pasan.
```

---

## Sesión GPU 1 (manual, ~09:30 a 13:30)

Sigue `docs/SESION_GPU.md`. Tope orientativo: 4 h (escenario B, fila "Montaje..." del plan).

Antes de crear:
- [ ] Precio en consola confirmado; `.env.gpu` listo; modelos A y B anotados.
- [ ] `docs/SESION_GPU.md` escrito (Prompt 11).

Durante:
- [ ] vLLM solo en 127.0.0.1 con `--api-key`; acceso por túnel SSH.
- [ ] Dos modelos probados; uno elegido y tag de imagen fijado.
- [ ] Números reales en `docs/BENCHMARKS.md`; N, K, R en `search/config.py`.

Al terminar (obligatorio antes de la tarde):
- [ ] `vllm.sh stop`.
- [ ] Instancia **destruida** (no solo apagada).
- [ ] Hora de fin y costo de la sesión anotados.
- [ ] Commit y push.

Si la imagen ROCm o vLLM no arranca en 45 min, documenta el error en `docs/BENCHMARKS.md`, destruye, y sigue con el bucle contra el mock. Reintenta en la sesión 2 con otro tag/modelo.

---

## Prompt 12: bucle de búsqueda contra el mock

**Hora:** 14:00 a 16:30 (150 min) · **OBLIGATORIO HOY**

```text
Objetivo: implementar el bucle de la sección 6 de docs/PLAN.md, operable 100% en local contra
el mock LLM (make mock-llm), sin GPU.

Archivos: search/loop.py, search/prompts.py (o equivalente), tests/test_search_loop.py,
ajustes menores en llm/client.py o sim/ solo si hacen falta.

Comportamiento (search.run_search o equivalente):
- política_0 = regla fija (baselines/fixed o la política default del plan).
- Para ronda en 1..R (R desde search/config.py):
  - Prompt con escenario + top-k políticas previas con métricas + análisis simple de fallas
    (paro por máquina, órdenes tardías) a partir de métricas ya simuladas.
  - candidatas = LLM.proponer(N) en paralelo con JSON Schema / response_format estricto.
  - Filtrar inválidas con el schema Pydantic (máx 5 reglas, umbrales en rango, sin campos extra).
  - métricas = simulate_many(válidas, K semillas) con ProcessPoolExecutor / SIM_WORKERS.
  - Actualizar top-k; registrar simulaciones gastadas y latencias.
- Al terminar: mejor = top-1. Holdout completo (300 + estrés) es del miércoles; hoy basta un
  holdout chico opcional (p. ej. 30 semillas) para no bloquear.
- API: run_search(config, llm_client, scenario, rng_seed) -> SearchResult con políticas,
  métricas por ronda, simulaciones_totales, mejor_politica, mejor_objetivo.

CLI: uv run python -m search.loop --seed 1 (o make search-mock) que imprime progreso por ronda
y escribe JSON en bench/results/search_mock_<fecha>.json.

Tests:
- Con mock determinista o ASGITransport: búsqueda corta (N=2, K=2, R=2) termina; políticas
  pasan el schema; simulaciones_totales coherente; misma semilla => mismo mejor_objetivo
  (o documenta qué no es bit-idéntico y por qué).
- Candidatas inválidas no tumban el bucle.

No hagas: Optuna, UI, Railway, tarjeta de operador con guard, SSE.

Aceptación: make mock-llm + búsqueda corta en local; pytest y ruff limpios; commit "prompt 12".
```

---

## Prompt 13: persistir la corrida en Postgres

**Hora:** 16:30 a 18:00 (90 min) · **OBLIGATORIO HOY**

```text
Objetivo: que una búsqueda completa quede grabada para replay futuro (MODE=replay el viernes).
Hoy solo persistencia y lectura; no hace falta la UI de replay.

Archivos: migraciones Alembic si faltan tablas/columnas, db/ models o repositorios,
search/ o worker/ que escriba al terminar, tests de db.

Modelo mínimo (ajusta nombres al esquema ya existente de jobs/policies/metrics/runs):
- runs (o search_runs): id, job_id, started_at, finished_at, config (N,K,R, modelo, seed),
  status, total_simulations, best_policy_id, best_objective, raw_json o filas hijas.
- Por ronda: candidatas (policy JSON), válidas/inválidas, métricas agregadas, latencias.
- policies: JSON de la política + hash o versión de schema.
- metrics: KPIs por política (y por evaluación train vs holdout si aplica).

Al terminar run_search (o un wrapper), abrir transacción y persistir lo necesario para
reproducir la curva de mejora sin re-ejecutar el LLM. Idempotencia: re-correr el mismo job_id
no duplica basura (o marca el run anterior superseded).

CLI: uv run python -m search.show_last_run (o similar) lista el último run con best_objective
y total_simulations.

Tests con Postgres de test: búsqueda N=2,K=2,R=2 queda consultable; make test pasa.

No hagas: UI HTMX, MODE=replay HTTP, Optuna, desplegar Railway.

Aceptación: tras una búsqueda mock hay filas en Postgres; show_last_run funciona;
alembic upgrade head limpio; commit "prompt 13".
```

---

## Prompt 14: worker ejecuta un job de búsqueda

**Hora:** 18:00 a 19:30 (90 min) · **OBLIGATORIO HOY**

```text
Objetivo: el hito del martes - una búsqueda de punta a punta disparada como job y guardada
en Postgres, con el worker existente (SKIP LOCKED), primero en local con mock.

Archivos: worker/ (handler de tipo job "search" o el que ya exista), api/ si hace falta
POST /jobs con type=search, tests de integración.

Flujo:
1. Encolar un job (CLI make enqueue-search o POST /jobs) con seed, scenario y SearchConfig
   (o defaults de search/config.py).
2. worker.main toma el job, corre run_search con LLMClient apuntando al mock
   (LLM_BASE_URL del .env), persiste el run (Prompt 13), marca job done (o failed con error).
3. Evidencia: logs por ronda; job.status=done; show_last_run muestra el resultado.

Si el worker aún solo tenía el baseline stub del lunes, extiéndelo sin romper ese path.

Tests: integración que encola, corre un ciclo del worker (o el handler), y afirma job done
+ run persistido. Usar N,K,R pequeños.

No hagas: conectar Railway salvo prueba corta de sslmode=require (no obligatoria hoy).
No Optuna. No UI.

Aceptación: en local, make mock-llm + make worker (o make dev) + encolar search => job done
y run en Postgres. pytest/ruff verdes. Commit "prompt 14". Ese es el hito del martes.
```

---

## Sesión GPU 2 (opcional, ~19:30 a 21:30)

Solo si el hito del Prompt 14 ya pasó en mock y quedan créditos/tiempo.

1. Crear instancia; anotar inicio y precio de consola.
2. `up.sh` + `vllm.sh start` con el **modelo ya elegido** en la sesión 1 (sin explorar).
3. Worker en la instancia con `DATABASE_URL` pública de Railway (`sslmode=require`) **o** plan B:
   Postgres local en la instancia y sync al final (`docs/PLAN.md` sección 8).
4. Una sola búsqueda con N,K,R fijados; confirmar run guardado.
5. `stop` + **destruir** instancia; anotar costo.

Si Railway público no conecta, no gastes la noche: deja el run en Postgres local de la
instancia, scp del dump o JSON, y documenta el plan B en `docs/BENCHMARKS.md`.

---

## Checklist de cierre (martes, ~22:00)

- [ ] Precio de consola confirmado; sección "Martes 13, MI300X" de BENCHMARKS llena con números reales (o error documentado si la GPU falló).
- [ ] Modelo estable + tag exacto de imagen vLLM anotados.
- [ ] N, K, R fijados en `search/config.py` (o defaults conscientes si no hubo GPU).
- [ ] Toda instancia creada hoy está **destruida**; costos anotados.
- [ ] Hito: al menos una búsqueda mock de punta a punta en Postgres (job done).
- [ ] Si hubo GPU 2: un run real referenciado en BENCHMARKS.
- [ ] Preguntas mandadas (o anotadas) al Discord de lablab.
- [ ] `docs/PENDIENTES_MIERCOLES.md`: líneas base (regla fija, Optuna, LLM sin feedback),
      evaluación holdout+estrés, calibración dataset público, curva de eficiencia, alinear
      Postgres de Railway a major 16 si hace falta.
- [ ] Sin `.env` ni claves en git; push al día.

## Qué queda para el miércoles

1. Líneas base con el mismo presupuesto de simulaciones (regla fija, Optuna, LLM sin retroalimentación).
2. Curva de eficiencia (mejor objetivo vs simulaciones gastadas).
3. Calibración con dataset público (AI4I 2020 o C-MAPSS) y declaración de límites.
4. Evaluación en 300 semillas reservadas + escenario perturbado; IC 95%.
5. Más corridas en GPU solo con lista escrita; destruir al terminar.
