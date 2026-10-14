# TwinVerdict: prompts del miércoles 14 oct (líneas base, curva, calibración, replay)

Plan de referencia: `docs/PLAN.md` (fila "Mié 14") y `docs/PENDIENTES_MIERCOLES.md` en el repo.

**Estado al arrancar (verificado en GitHub `focampok/twinverdict`, `main` al cierre del mar 13):** prompts 11 a 14 hechos. Hay una búsqueda mock de punta a punta en Postgres: job `78fea53a`, 40.8 min, 115_500 simulaciones con K=300. El holdout y el estrés ya están validados, con el % a tiempo pasando de 46% a 99%. Perfiles en `search/config.py`: `default` (N=48, K=180, R=8), `final` (K=300) y `smoke` (N=2, K=2, R=2). Cada job guarda N/K/R, workers, modelo, perfil, semillas, commit y s/sim. `Qwen/Qwen3-8B` es el modelo por defecto; el 32B se compara por calidad en la sesión GPU 2. La instancia del martes está destruida. Linux nativo, sin docker compose. `infra/gpu/gpu.sh bench-sim` existe pero no se ha corrido.

Huecos reales en el repo: `baselines/` y `eval/` solo tienen `__init__.py`, `sim/calibration.py` es un stub que devuelve los defaults de `PlantConfig`, `guard/` está vacío y `optuna` todavía no está en `pyproject.toml`. No repitas lo del martes (holdout de 78fea53a, schema WEIGHTED, perfiles, reproducibilidad).

**Objetivo de hoy:** (1) líneas base con **el mismo presupuesto de simulaciones** que el bucle: regla fija (ya es la política 0), Optuna TPE y LLM sin retroalimentación; (2) curva de eficiencia y tabla de los cuatro métodos; (3) calibración real con AI4I 2020 y límites declarados; (4) una corrida congelada para replay y un snapshot de la tarjeta de operador. **Hito:** tabla de 4 métodos con presupuesto igual en `docs/BENCHMARKS.md`.

**Presupuesto igual (perfil `default`):** `K + N*R*K = 180 + 48*8*180 = 69_300` simulaciones de entrenamiento por método, en las mismas semillas de entrenamiento (`range(seed, seed+K)`) y el escenario `base`. Si una corrida usa `final` (K=300), las líneas base de esa corrida usan el mismo K. A 0.0212 s/sim sostenido, cada método tarda unos 24.5 min en la laptop con `SIM_WORKERS=16`.

**Regla de oro:** código y pruebas en local contra el mock. La GPU de hoy es opcional y solo para comparar 8B contra 32B por calidad. Si se crea la instancia, se **destruye** al terminar.

## Agenda del día

| Hora (GT) | Paso | Prioridad |
|---|---|---|
| ~09:00 a 09:15 | Paso 0: alcance actual, `SIM_WORKERS=16`, `make mock-llm` arriba | Obligatorio |
| 09:15 a 11:30 | Prompt 15: Optuna con presupuesto igual | Obligatorio |
| 11:30 a 13:00 | Prompt 16: LLM sin retroalimentación con presupuesto igual | Obligatorio |
| 13:00 a 13:45 | Comida (las corridas default de 15 y 16 pueden seguir en segundo plano) | |
| 13:45 a 15:30 | Prompt 17: curva de eficiencia y tabla de comparación | Obligatorio |
| 15:30 a 17:15 | Prompt 18: calibración con AI4I 2020 | Obligatorio |
| 17:15 a 18:45 | Prompt 19: replay completo, corrida congelada, snapshot de la tarjeta | Obligatorio |
| 19:00 a 21:30 | Sesión GPU 2: 8B vs 32B por holdout en la MI300X | Opcional, solo si 15 a 17 ya están |
| 21:30 a 22:00 | Checklist de cierre y `docs/PENDIENTES_JUEVES.md` | Obligatorio |

La hora de inicio es flexible: si arrancas más tarde, corre todo el bloque y recorta la sesión GPU 2, no los prompts.

**Corte del plan (mié noche):** si las líneas base no caben, Optuna queda solo con parámetros numéricos (sin la regla de despacho categórica) y "LLM sin retroalimentación" sale del video (queda en el README si se corrió).

## Paso 0 manual (~09:00 a 09:15)

1. `git pull` en `main`. Confirma que `.env` tiene `SIM_WORKERS=16` y `LLM_BASE_URL` del mock (`http://localhost:8001/v1`).
2. En una terminal, `make mock-llm`. Postgres local arriba (`make db`).
3. Pega el bloque de abajo en `CLAUDE.md` o en la regla de `.cursor/`.
4. Lanza las corridas largas en segundo plano con `nohup ... &` o `tmux`, para que no bloqueen la terminal mientras el agente sigue con el siguiente prompt.

### Alcance actual (pegar en el archivo de contexto)

```markdown
## Alcance actual (miércoles 14)
Líneas base con el mismo presupuesto de simulaciones que el bucle (perfil default:
N=48, K=180, R=8, 69_300 sims de entrenamiento): regla fija (ya existe), Optuna TPE
(numéricos + regla de despacho categórica) y LLM sin retroalimentación. Curva del
mejor objetivo contra simulaciones y sims al 90% del mejor. Calibración desgaste→riesgo
con AI4I 2020 (o C-MAPSS), con límites declarados. Replay: congelar una corrida y un
snapshot JSON para la tarjeta de operador (% a tiempo 46% → 99%).
GPU opcional al final: worker nativo con SIM_WORKERS=18, 8B vs 32B por holdout, destruir.
No implementar: UI HTMX, aprobación en pantalla, Railway en producción, SSE,
premio de Google, docker compose, fine-tuning, código generado por el LLM.
```

## Cómo usar los prompts

Uno por uno. Revisa el diff y corre `uv run ruff check .`, `uv run ruff format --check .` y `uv run pytest -q` (o `make lint` y `make test`) antes de cada commit. Un commit por prompt (`git commit -m "prompt 15: optuna baseline"`) y push. No reescribas historia ya subida. En `docs/BENCHMARKS.md` solo van números medidos; si algo no corrió, se deja el hueco y se dice por qué.

---

## Prompt 15: línea base Optuna con presupuesto igual

**Hora:** 09:15 a 11:30 (~135 min) · **OBLIGATORIO HOY**

```text
Objetivo: Optuna (TPE) como línea base justa del bucle LLM. Mismo presupuesto de
simulaciones de entrenamiento que una búsqueda del perfil elegido:
total_train_sims = K + N*R*K (default: 69_300). Optuna solo ajusta parámetros de una
Policy válida; nunca genera código ni reglas condicionales.

Archivos:
- baselines/budget.py: total_train_sims(config: SearchConfig) -> int, compartido con
  el Prompt 16 y el 17.
- baselines/optuna_search.py: run_optuna(config, scenario, rng_seed, workers) y CLI.
- tests/test_baselines_optuna.py.
- pyproject.toml y uv.lock: `uv add optuna`.
- docs/BENCHMARKS.md: sección "Miércoles 14, Optuna" (se llena con la corrida real).

Espacio de búsqueda (rangos tomados de policy/schema.py, no inventados):
- Numéricos: maintenance.pm_wear_threshold por máquina (M1 a M5),
  maintenance.max_pm_per_shift y, si la regla es WEIGHTED, dispatch.weights
  (due_date, wear_risk, setup), normalizados a suma 1.
- Categórico: dispatch.rule en {EDD, SPT, WEIGHTED, CRITICAL_RATIO}.
- rules: lista vacía (o la de fixed_rule_policy()). Esa es la ventaja estructural del
  LLM; escríbelo en un comentario y en BENCHMARKS.
- Construye la Policy y valídala con Pydantic antes de simular. Si no valida, el trial
  se marca como fallido y NO gasta simulaciones.

Evaluación:
- Cada trial llama a search.loop.evaluate_policy con las mismas train_seeds que
  run_search (range(rng_seed, rng_seed + K)), scenario "base" y SIM_WORKERS de
  Settings. El objetivo es composite_objective medio (el mismo de sim/objective.py).
  Maximizar.
- El trial 0 es fixed_rule_policy() (study.enqueue_trial), igual que la política 0
  del bucle. Número de trials = total_train_sims // K (default: 385). Al final,
  simulations_total == total_train_sims.
- TPESampler(seed=rng_seed) para que la misma semilla dé el mismo resultado.

Salida:
- bench/results/optuna_<perfil>_seed<seed>_<fecha>.json con best_policy,
  best_objective, fixed_objective, simulations_total, historial por trial
  (trial, sims_acumuladas, objetivo, best_so_far) y los metadatos de
  search/repro.py (N, K, R, perfil, modelo "none", semillas, workers, commit, s/sim).
- Si el worker ya maneja tipos de job, añade el tipo "baseline_optuna" con el mismo
  esquema de persistencia de search/store.py. Si eso complica, déjalo en JSON y anótalo.

CLI: uv run python -m baselines.optuna_search --profile default --seed 1
(--profile smoke para tests). Target opcional: make baseline-optuna.

Tests (perfil smoke):
- Termina y simulations_total == total_train_sims(smoke).
- best_policy pasa el schema; WEIGHTED siempre lleva weights.
- Misma semilla, mismo best_objective.
- Un trial inválido no gasta simulaciones ni tumba el estudio.

No hagas: cambiar el simulador o los pesos del objetivo, reglas condicionales en
Optuna, curva (Prompt 17), UI, GPU. Si Optuna gana o empata, se reporta tal cual.

Aceptación: ruff y pytest verdes; corrida smoke en local; la corrida default lanzada
en segundo plano (nohup) y, cuando termine, best_objective, fixed_objective y sims en
BENCHMARKS. Commit "prompt 15: optuna baseline".
```

---

## Prompt 16: línea base LLM sin retroalimentación

**Hora:** 11:30 a 13:00 (~90 min) · **OBLIGATORIO HOY**

```text
Objetivo: medir cuánto aporta el bucle. El LLM propone N*R políticas con un solo
prompt fijo, sin ver métricas ni top-k de rondas previas. Mismo presupuesto de
simulaciones. En local contra el mock (LLM_BASE_URL del .env).

Archivos:
- search/prompts.py: build_oneshot_prompt(scenario), con el escenario, la regla fija
  como referencia y las instrucciones del schema. Sin métricas, sin top-k, sin
  análisis de fallas.
- baselines/llm_nofeedback.py: run_llm_nofeedback(config, llm_client, scenario,
  rng_seed, workers) y CLI.
- tests/test_baselines_llm_nofeedback.py.
- docs/BENCHMARKS.md: sección "Miércoles 14, LLM sin retroalimentación".

Comportamiento:
1. Evaluar fixed_rule_policy() en las K semillas de entrenamiento (cuenta en el
   presupuesto).
2. Pedir N*R propuestas (default 384) con LLMClient.propose en R lotes de N, todos con
   el mismo prompt one-shot. Cambia solo la semilla de muestreo por lote, para que no
   salgan 384 copias iguales. Usa el mismo modelo y la misma temperatura que el bucle.
3. Filtrar inválidas con el schema y simular solo las válidas (K semillas cada una)
   con evaluate_policy. simulations_total <= total_train_sims(config). Si hay menos
   válidas que N*R, no se rellena: se reporta la tasa.
4. Historial por lote: (lote, sims_acumuladas, best_so_far) para la curva.
5. Salida: bench/results/llm_nofeedback_<perfil>_seed<seed>_<fecha>.json con el mismo
   formato y metadatos que el Prompt 15 (modelo = LLM_MODEL). Tipo de job opcional
   "baseline_llm_nofeedback".

CLI: uv run python -m baselines.llm_nofeedback --profile default --seed 1.
Target opcional: make baseline-llm-nf.

Tests (smoke, mock):
- El prompt one-shot no contiene objetivos ni KPIs de candidatas.
- simulations_total <= total_train_sims y es múltiplo de K.
- Las políticas evaluadas pasan el schema; las inválidas no tumban la corrida.
- Misma semilla y mock determinista dan el mismo best_objective.

No hagas: reutilizar run_search con R rondas (eso ya es el bucle), Optuna, UI, GPU.

Aceptación: ruff y pytest verdes; smoke en local; default lanzado en segundo plano y
números en BENCHMARKS al terminar. Commit "prompt 16: llm no-feedback baseline".
```

Nota: contra el mock, el LLM sin retroalimentación puede quedar muy cerca del bucle, porque el mock no "aprende" del prompt. Eso es esperado y se dice en BENCHMARKS. La comparación que cuenta para el pitch se repite con vLLM real en la sesión GPU 2 o en las corridas finales del jueves.

---

## Prompt 17: curva de eficiencia y tabla de comparación

**Hora:** 13:45 a 15:30 (~105 min) · **OBLIGATORIO HOY**

```text
Objetivo: la métrica de eficiencia de la sección 7 del plan. Para cada método, la
curva del mejor objetivo encontrado contra simulaciones gastadas, y las simulaciones
que necesita para llegar al 90% del mejor. Cuatro métodos con presupuesto igual:
regla fija, Optuna, LLM sin retroalimentación y LLM con bucle.

Archivos:
- eval/efficiency.py: curve(history) -> list[(sims, best_so_far)],
  sims_to_fraction(curve, target) -> int | None y main() con CLI.
- tests/test_efficiency.py.
- docs/BENCHMARKS.md: sección "Miércoles 14, curva de eficiencia" con tabla y la ruta
  de la figura.
- bench/results/efficiency_<fecha>.json y .png (matplotlib solo como dependencia dev;
  si no quieres sumar dependencias, deja el JSON y la figura sale el jueves en Chart.js).

Especificación:
1. Entradas: los JSON del Prompt 15 y 16, y una búsqueda con bucle del MISMO perfil y
   semilla. El job 78fea53a usó K=300, así que no es comparable con default: corre una
   búsqueda nueva con make enqueue-search o search.loop con perfil default y seed 1, o
   compara todo en final si hay tiempo. La curva del bucle se reconstruye de las rondas
   persistidas (sims_spent y evaluated por ronda en search_runs/runs); no re-ejecutes
   el LLM.
2. Regla fija: punto único en K sims, que se extiende horizontal hasta el presupuesto.
3. Umbral fijado ANTES de mirar resultados: target = fixed + 0.9 * (best_global - fixed),
   donde best_global es el máximo entre los cuatro métodos. Este umbral sobre la mejora
   evita depender de que el objetivo no está acotado a 0 a 1. Si un método no llega,
   pon "no alcanza".
4. Holdout de los ganadores: evalúa la mejor política de cada método en las 300
   semillas de holdout (1_000_001 en adelante, las de run_search) con IC 95% por
   bootstrap (2000 remuestreos, PCG64(0), igual que la validación del martes; reutiliza
   ese código si ya existe). Son 4 x 300 = 1200 sims extra, fuera del presupuesto de
   búsqueda; anótalo.
5. Tabla en BENCHMARKS: método | mejor train | holdout (IC 95%) | % a tiempo holdout |
   sims gastadas | sims al 90% | notas.
6. Párrafo honesto debajo de la tabla. Si Optuna empata o gana, el mensaje pasa a
   "el LLM llega a un resultado comparable con X sims y explica el porqué con reglas
   legibles". Si el bucle gana, cuánto y en qué KPI. Aclara que el LLM es el mock.
7. Re-ejecutable sin GPU: uv run python -m eval.efficiency --results-dir bench/results
   --profile default --seed 1. Target opcional: make efficiency.

Tests:
- best_so_far es no decreciente.
- sims_to_fraction con historial sintético devuelve el primer cruce; None si no cruza.
- La regla fija se representa bien con un único punto.

No hagas: UI, cambiar pesos, re-correr el holdout del martes, GPU.

Aceptación: tabla de 4 métodos con números reales (perfil default; smoke solo si
default no terminó, marcado como parcial); el script re-genera el JSON; ruff y pytest
verdes. Commit "prompt 17: efficiency curve and comparison".
```

---

## Prompt 18: calibración con AI4I 2020

**Hora:** 15:30 a 17:15 (~105 min) · **OBLIGATORIO HOY**

```text
Objetivo: reemplazar el stub de sim/calibration.py por un ajuste real de la curva
desgaste→riesgo de falla con un dataset público. Preferido AI4I 2020 Predictive
Maintenance (UCI, 10_000 filas, columna "Tool wear [min]" y "Machine failure", con
los modos TWF/HDF/PWF/OSF/RNF). C-MAPSS solo si AI4I no se puede descargar.
Documentar qué se calibró y qué no. No afirmar un despliegue real.

Archivos:
- bench/download_ai4i.py: descarga a data/raw/ai4i2020.csv, imprime sha256. data/raw/
  va en .gitignore. Documenta URL y fecha.
- sim/calibration.py: fit_failure_curve(dataset_path) -> FailureParams real.
- tests/fixtures/ai4i_sample.csv (~200 filas sintéticas con las mismas columnas) y
  tests/test_calibration.py. CI no descarga nada.
- docs/CALIBRATION.md (nuevo) y un enlace desde docs/BENCHMARKS.md.
- sim/config.py solo si hace falta un modo para cargar los params calibrados
  (p. ej. sim/calibrated_params.json versionado, pequeño).

Método (simple y auditable):
1. Normaliza tool wear a [0, 1] con su máximo observado (u otra escala que coincida
   con el desgaste del simulador; explícalo).
2. Ajusta una logística P(falla | desgaste) = base + (1 - base) * sigmoid(steepness *
   (wear - midpoint)) por máxima verosimilitud (numpy/scipy si ya están; si no, grid
   search). Usa la falla total o TWF + RNF; justifica la elección.
3. Convierte la probabilidad por registro a tasa por minuto de simulación, con la
   suposición documentada. Si la conversión no tiene soporte en los datos, el
   parámetro queda como supuesto y se dice.
4. Escribe sim/calibrated_params.json con midpoint, steepness, base_per_min, fuente,
   fecha y sha256 del CSV.

docs/CALIBRATION.md, en castellano claro:
- Dataset, fuente, licencia, filas usadas y comando de descarga.
- Qué parámetros salieron del ajuste y su valor antes y después.
- Qué sigue siendo supuesto de planta simulada: demanda, setups, 5 máquinas, costos,
  tiempos de reparación, reglas de despacho.
- Qué NO se afirma: planta real, ROI de un cliente, datos propietarios.

Impacto: re-evalúa la regla fija y la mejor política del martes en 100 semillas con
los params calibrados. Anota en BENCHMARKS si el % a tiempo y el objetivo cambian. Si
la historia 46% → 99% se mueve, dilo y decide si el resto de la semana usa los
params calibrados (recomendado si el cambio es razonable).

Tests: el ajuste sobre el fixture da params en rangos sensatos (0 < midpoint < 1,
steepness > 0); simulate() con params calibrados sigue determinista por semilla; la
conservación de órdenes se cumple.

No hagas: modelos de ML como política, deep learning, UI, GPU.

Aceptación: stub reemplazado; CALIBRATION.md honesto; ruff y pytest verdes.
Commit "prompt 18: ai4i calibration".
```

Si AI4I no se descarga (red, URL cambiada), el agente documenta el intento, usa C-MAPSS o deja el ajuste con el fixture y lo marca como pendiente, sin inventar parámetros.

---

## Prompt 19: replay completo y snapshot de la tarjeta de operador

**Hora:** 17:15 a 18:45 (~90 min) · **OBLIGATORIO HOY**

```text
Objetivo: que el jueves la UI solo lea datos. Revisar que la persistencia del martes
alcance para reproducir una corrida sin LLM ni simulación, congelar una corrida y dejar
un JSON con las métricas de la tarjeta de operador. Hoy no se construye la UI.

Archivos:
- docs/REPLAY.md (nuevo, corto): lista de lo que guarda cada corrida y qué lo lee.
- search/replay.py: load_replay(job_id) -> dict estable (job, config reproducible,
  rondas con prompt, candidatas válidas e inválidas, latencias, sims_spent, métricas
  por política, mejor política, holdout si existe, curva de eficiencia).
- search/freeze_run.py: CLI que escribe bench/results/replay_<job_id>.json y
  bench/results/operator_card_<job_id>.json.
- Migración Alembic solo si falta algo (p. ej. latencias por ronda, invalid por ronda,
  baselines asociadas al job).
- tests/test_replay.py.

Revisión de huecos (marca cada uno en REPLAY.md como OK o CORREGIDO):
prompts por ronda, candidatas válidas e inválidas con motivo, latencias, sims por
ronda y totales, KPIs por política, holdout y estrés de la mejor, metadatos de
search/repro.py, y enlace a las líneas base del Prompt 15 y 16.

operator_card_<job_id>.json, solo con números medidos (sin texto del LLM todavía):
- on_time_fixed y on_time_best (train y holdout), throughput, paro no planificado,
  paro planificado, mantenimientos preventivos, fallas y costo, para regla fija y mejor.
- Objetivo holdout con IC 95% de ambas.
- Resumen legible de la política ganadora (regla de despacho, umbrales, max_pm_per_shift).
- Nota de estrés: en estrés el hueco lo lleva el throughput, no el % a tiempo, así que
  la tarjeta no promete el mismo salto bajo pico.
- Una sección "numbers" plana {nombre: valor} que el jueves usará guard/numbers.py
  para verificar el texto.
Corrida a congelar: la búsqueda default del Prompt 17 si terminó; si no, 78fea53a.
Usa los números del martes solo para 78fea53a.

Tests: load_replay devuelve las claves mínimas; freeze es idempotente (dos veces, mismo
archivo y sin filas duplicadas); todos los valores de "numbers" salen de la base, no
están escritos a mano.

No hagas: vistas Jinja/HTMX, POST /policies/{id}/approve, Chart.js, MODE=replay HTTP
en Railway, SSE.

Aceptación: REPLAY.md con todo en OK; los dos JSON commiteados; ruff y pytest verdes.
Commit "prompt 19: replay freeze and operator card snapshot".
```

---

## Sesión GPU 2 (opcional, manual, ~19:00 a 21:30)

**Solo si** los Prompts 15 a 17 ya tienen la tabla de 4 métodos **y** quieres gastar unas 2 a 3 h de crédito (~$4 a $6 a $1.99/h). Si no, se pasa a las corridas finales del jueves sin perder nada.

Antes de crear:
- [ ] Prompts 15 a 17 commiteados.
- [ ] Lista de qué medir escrita (esta sección). Hora de inicio anotada.
- [ ] `infra/gpu/.env.gpu` listo (nunca al repo).

Pasos:
1. Consola de DigitalOcean / AMD Developer Cloud: **MI300X x1, bajo demanda**, imagen **vLLM 0.27.1 1-Click**. Anota IP, precio por hora y hora de inicio.
2. En la laptop: `GPU_IP=<nueva> infra/gpu/gpu.sh tunnel`. En la GPU, crea la clave como el martes (`/root/vllm.key`, sin pegarla en el chat).
3. `gpu.sh serve Qwen/Qwen3-8B` y `gpu.sh wait`. Comprueba con `gpu.sh status`.
4. `gpu.sh bench-sim` (18 workers, primera vez). Con el s/sim de la instancia decide perfil `default` o `final`.
5. Worker nativo en la instancia según `docs/SESION_GPU.md`: `up.sh`, `SIM_WORKERS=18`, Postgres de Railway con `sslmode=require` o Postgres local y sync al final.
6. Búsqueda A: `LLM_MODEL=Qwen/Qwen3-8B`, perfil elegido, `--seed 1`.
7. `gpu.sh serve Qwen/Qwen3-32B` y `gpu.sh wait`. Búsqueda B: mismo perfil, misma semilla, `LLM_MODEL=Qwen/Qwen3-32B` (el cliente ya manda `enable_thinking=false`).
8. Si sobra tiempo dentro del tope: LLM sin retroalimentación con el 8B real (mismo perfil y semilla), que es la comparación que el mock no puede dar.
9. `gpu.sh stop`, **destruir** la instancia en la consola, `gpu.sh untunnel`. Anota hora de fin y costo.

Después, pídele al agente:

```text
Sin GPU. Compara las búsquedas 8B y 32B de la sesión GPU 2 (mismo perfil y semilla):
objetivo train, holdout con IC 95% bootstrap, % a tiempo, tasa de JSON válido, sims y
minutos. Añádelas a la tabla del Prompt 17 como "bucle 8B (vLLM)" y "bucle 32B (vLLM)".
Escribe docs/BENCHMARKS.md sección "Sesión GPU 2, 8B vs 32B por calidad". LLM_MODEL por
defecto solo cambia a 32B si su IC de holdout queda por encima del IC del 8B. Anota
costo y horas de la sesión. ruff, pytest, commit "gpu session 2: 8b vs 32b".
```

Si vLLM o Postgres no funcionan en 45 min: documenta el error en BENCHMARKS, destruye la instancia y sigue en local.

---

## Checklist de cierre (miércoles, ~22:00)

- [ ] Optuna con presupuesto igual: resultado en BENCHMARKS (default, o smoke marcado como parcial).
- [ ] LLM sin retroalimentación con presupuesto igual: resultado en BENCHMARKS.
- [ ] Tabla de 4 métodos con holdout, sims al 90% y párrafo honesto (también si Optuna gana o empata).
- [ ] `eval.efficiency` re-genera la tabla sin GPU.
- [ ] `docs/CALIBRATION.md` con dataset, parámetros ajustados y límites; impacto en la historia 46% → 99% anotado.
- [ ] Corrida congelada (`replay_*.json`) y `operator_card_*.json` commiteados.
- [ ] Si hubo GPU 2: comparación 8B vs 32B, instancia **destruida**, costo anotado.
- [ ] Sin `.env` ni claves en git; ruff y pytest verdes; push a `main`.
- [ ] `docs/PENDIENTES_JUEVES.md` escrito con el prompt de abajo.

### Prompt de cierre: `docs/PENDIENTES_JUEVES.md`

```text
Escribe docs/PENDIENTES_JUEVES.md con el estado real de hoy (commits y números de
BENCHMARKS, no inventes) y, en orden:
1. UI con polling (FastAPI + Jinja2 + HTMX): la tarjeta de operador PRIMERO, leyendo
   operator_card_*.json: recomendación, números verificados por guard/numbers.py contra
   la sección "numbers", botón aprobar/rechazar (POST /policies/{id}/approve).
2. guard/numbers.py: todo número del texto de la tarjeta debe existir en el diccionario
   de métricas; si no, se descarta el texto. Tests.
3. Vista de búsqueda en vivo (polling de GET /jobs/{id}/status) y curva de mejora en
   Chart.js desde el payload de replay.
4. Vista de comparación: fija, Optuna, LLM sin retroalimentación y bucle, con IC.
5. Panel de hardware: tokens/s de /metrics de vLLM y rocm-smi; si no hay GPU, captura
   estática de la sesión GPU (corte 3 del plan).
6. Corridas finales en la GPU si hay créditos: perfil final, mismas semillas, líneas
   base en la misma sesión; destruir al terminar.
7. Decisión del premio de Google solo si Discord ya respondió y no toca vLLM en AMD.
8. Railway con MODE=replay queda para el viernes.
Commit y push.
```

## Qué queda para el jueves

1. UI con polling: tarjeta de operador primero, aprobación humana, curva y comparación.
2. `guard/numbers.py` real sobre el snapshot de la tarjeta.
3. Panel de hardware (en vivo o captura).
4. Corridas finales en la GPU con lista escrita y destrucción al terminar.
5. Decisión del premio de Google.
