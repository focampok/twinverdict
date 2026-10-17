# Replay: qué guarda una corrida y quién lo lee

El jueves la UI solo lee datos: nada de llamar al LLM ni de simular para mostrar una corrida.
Este documento lista qué queda guardado, dónde, quién lo lee y qué huecos había.

## Checklist de demo

1. `cp .env.example .env` con `MODE=replay` y `REPLAY_JOB_ID=c0c92625-de22-4520-accb-6a17c1a76428`.
2. `make setup && make db`.
3. `make web`.
4. Abrir http://localhost:8000/ y ver la tarjeta, el badge "Recorded run · real vLLM (Qwen3-8B on MI300X)" y la curva.
5. Sin GPU ni LLM: la tarjeta y la curva salen de los JSON versionados; `POST /jobs` responde 503.

## Dónde vive cada cosa

| Tabla | Qué guarda | Quién lo escribe | Quién lo lee |
|---|---|---|---|
| `jobs` | tipo (`search`/`baseline`), estado, parámetros, error | `worker.enqueue`, `worker.main` | `load_replay`, `search.store.latest_done` |
| `search_runs` | una fila por corrida: config reproducible, `total_simulations`, `best_objective`, `best_policy_id` | `search.store.persist_search` | `load_replay`, `format_last` |
| `policies` | una fila por política evaluada: `round`, `source`, JSON de la política | `search.store.persist_search` | `load_replay` |
| `metrics` | una fila por política y conjunto de semillas (`train`/`holdout`/`stress`): objetivo, IC, KPIs, simulaciones | `search.store.persist_search` | `load_replay`, la tarjeta |
| `runs` | eventos del job. `event_type='round'` trae el prompt, candidatas, latencias y sims | `worker.main`, `search.store.persist_search` | `load_replay` |

Comandos:

```bash
uv run python -m search.freeze_run              # la última corrida con status done
uv run python -m search.freeze_run <job_id>     # una concreta
```

Escribe `bench/results/replay_<job_id>.json` y `bench/results/operator_card_<job_id>.json`.
Los dos **sí se versionan** (son el insumo de la UI; el resto de `bench/results` está ignorado).

## Revisión de huecos

| Hueco | Estado | Dónde |
|---|---|---|
| Prompts por ronda | **OK** | `runs.payload.prompt`, `event_type='round'` |
| Candidatas válidas e inválidas con motivo | **OK** | `runs.payload.valid` (JSONs) y `runs.payload.invalid` (`content` + `error`) |
| Latencias por ronda | **OK** | `runs.payload.latencies_s` |
| Sims por ronda y totales | **OK** | `runs.payload.sims_spent` y `search_runs.total_simulations` |
| KPIs por política | **OK** | `metrics.kpis` |
| Holdout y estrés de la mejor | **CORREGIDO** | ver abajo |
| Holdout y estrés de la regla fija | **CORREGIDO** | ver abajo |
| Metadatos de `search/repro.py` | **OK** | `search_runs.config` |
| Enlace a las líneas base (15 y 16) | **CORREGIDO** | ver abajo |

### CORREGIDO: el estrés no se escribía

`metrics.seed_set` ya admitía `'stress'` desde la migración `c8e4a1b77d02`, pero **nada lo
escribía**: `run_search` solo evaluaba la mejor política en holdout, y la tarjeta necesita
además el estrés.

Ahora `run_search` evalúa **la mejor política y la regla fija** en holdout y en estrés (+30%
fallas, demanda ×1.5), en las mismas semillas, y `persist_search` guarda las cuatro filas. La
regla fija hacía falta porque la tarjeta compara las dos políticas: sin ella no había
`on_time_fixed` en holdout, que es el 46% del titular.

Las cuatro evaluaciones quedan **fuera del presupuesto de entrenamiento** pero se suman a
`simulations_total`, la misma convención que ya usaba el holdout. Es decir:
`total_simulations = entrenamiento + 4 × semillas_de_holdout`.

**No hizo falta migración de Alembic**: el `CheckConstraint` ya permitía los tres valores de
`seed_set`. Lo que cambió son los escritores, no el esquema.

### CORREGIDO: las líneas base no viven en la base

Optuna y el LLM sin retroalimentación (Prompts 15 y 16) escriben un JSON, no una fila. No se
les añadió una tabla: `load_replay` las enlaza por convención de nombre de archivo
(`optuna_<perfil>_seed<seed>_*.json` y `llm_nofeedback_<perfil>_seed<seed>_*.json` en
`bench/results`) y deja en `replay["baselines"]` la ruta, el método, el mejor objetivo y la
fuente del LLM de cada una. Si el archivo no está, el valor es `null` en vez de inventarse.

## Qué devuelve `load_replay(job_id)`

Claves estables, pensadas para que la UI no tenga que saber nada del esquema:

- `job`: id, tipo, estado, parámetros, fechas y error.
- `config`: el bloque reproducible de `search/repro.py` (N, K, R, perfil, modelo, semillas,
  workers, commit, s/sim, endpoint y `llm_source`).
- `run`: estado, fechas, `total_simulations`, `best_objective`, `best_policy_id`.
- `rounds`: por ronda, `prompt`, `valid`, `invalid`, `latencies_s`, `sims_spent`, `objectives`.
- `policies`: todas las políticas evaluadas con sus métricas por conjunto de semillas.
- `best_policy` / `best_metrics` y `fixed_policy` / `fixed_metrics`.
- `curve`: mejor objetivo contra simulaciones, reconstruida de las rondas persistidas.
- `baselines`: el enlace descrito arriba.
- `events`: la línea de tiempo del job.

## La tarjeta de operador

`operator_card_<job_id>.json` lleva **solo números medidos**, todavía sin texto del LLM:

- `fixed` y `best`, cada uno con `train`, `holdout` y `stress`: objetivo, IC 95%, y los KPIs
  (% a tiempo, throughput, paro no planificado, paro planificado, preventivos, costo, fallas).
- `objective_holdout`: el objetivo en holdout de las dos políticas con su intervalo.

El IC de la tarjeta es el analítico de `run_search` (media ± 1.96·s/√n), el que ya guardaba el
job del martes. La tabla de eficiencia usa bootstrap de 2000 remuestreos. Los dos coinciden
hasta el tercer decimal (por ejemplo 0.9579 [0.9435, 0.9723] contra [0.9439, 0.9715]), y la
diferencia es el método del intervalo, no los datos.
- `winning_policy`: regla de despacho, pesos, umbrales por máquina, `max_pm_per_shift` y
  cuántas reglas condicionales trae, más un `texto` corto.
- `stress_note`: en estrés el hueco lo lleva el throughput, no el % a tiempo, así que la
  tarjeta no promete el mismo salto bajo pico. Los `delta_throughput_stress` y
  `delta_on_time_stress` de `numbers` son la base medida de esa frase.
- `numbers`: plano `{nombre: valor}` con todo lo anterior más los umbrales por máquina y los
  deltas. El jueves `guard/numbers.py` verifica el texto contra este mapa; por eso
  **ningún número de la tarjeta está escrito a mano**, y hay un test que los recomputa desde
  `metrics` y los compara uno a uno. El texto de la UI pasa por `guard/numbers.py`.

## Operación

- Congelar es idempotente: escribe dos archivos y **no toca la base**. Congelar dos veces deja
  los mismos bytes y no añade filas.
- Los tests marcados `db` hacen `TRUNCATE` de las tablas al empezar, así que **correr la suite
  borra las corridas persistidas**. Por eso el job `78fea53a` del martes ya no está en la base
  local. Lo durable es el JSON congelado, y por eso se versiona.
- Si se vuelve a congelar la misma corrida después de un `TRUNCATE`, `load_replay` falla con
  "no tiene corrida persistida". Es correcto: no se puede inventar lo que ya no está.
