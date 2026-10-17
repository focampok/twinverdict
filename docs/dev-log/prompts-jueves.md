# TwinVerdict: prompts del jueves 15 oct, v2 (solo UI/UX)

Reemplaza a `prompts-jueves.md`. Esa versión se escribió antes de las sesiones GPU 2 y GPU 4 del miércoles en la noche y ya no cuadra con `main`.

**Estado verificado en GitHub `focampok/twinverdict`, `main`, tip `f770867` (jue 15, 11:40 GT):**
- Corte de calibración hecho (`b0fd30e`): `PlantConfig` default = midpoint 0.95 / steepness 18. El Prompt 20 viejo ya no se corre.
- Corrida oficial del bucle: job `285d1787-5d7c-464a-9897-4c585663f088`, vLLM real Qwen3-8B, planta calibrada. % a tiempo holdout **50.6% → 98.8%**. Tabla en `docs/BENCHMARKS.md` (sección GPU 4). `docs/PENDIENTES_JUEVES.md` dice: hoy solo UI/UX, sin GPU, sin re-correr búsquedas ni baselines.
- **Hueco real:** en `main` solo están `operator_card_c43bd2f0-….json` y `replay_c43bd2f0-….json` (la corrida vieja, planta sin calibrar). **No están** `operator_card_285d1787-….json` ni `replay_285d1787-….json` (404 en GitHub). Y `bench/results/efficiency_20261015.json` queda fuera de git por `.gitignore` (`bench/results/*.json`, con excepción solo para `replay_*` y `operator_card_*`). Si no se arregla, la UI local puede funcionar pero el deploy de Railway del viernes mostraría la corrida vieja o fallaría sin la curva.

## Agenda (desde ~12:00)

| Hora (GT) | Paso | Prioridad |
|---|---|---|
| 12:00 a 12:20 | Paso 0: congelar y versionar los artefactos de 285d1787 | Obligatorio |
| 12:20 a 13:15 | Prompt 21: `guard/numbers.py` + texto de tarjeta | Obligatorio |
| 13:15 a 14:00 | Comida | |
| 14:00 a 16:15 | Prompt 22: UI tarjeta de operador (HTMX + aprobar/rechazar) | Obligatorio |
| 16:15 a 17:30 | Prompt 23: curva Chart.js + tabla de cuatro métodos | Obligatorio |
| 17:30 a 18:30 | Prompt 24: `MODE=replay` end-to-end y badge REPLAY | Obligatorio |
| 18:30 a 20:30 | Opcional: prerequisito animación 2D, o las 34 inválidas de la ronda 2 | Opcional |
| 20:30 a 21:30 | Checklist y `docs/PENDIENTES_VIERNES.md` | Obligatorio |

Recorte si no da: tarjeta + curva primero; aprobar/rechazar puede quedar como stub.

## Paso 0 (~12:00 a 12:20)

1. `git pull` en `main`. `.env` con `MODE=replay`.
2. Revisa si en local existen `bench/results/operator_card_285d1787-5d7c-464a-9897-4c585663f088.json` y `bench/results/replay_285d1787-5d7c-464a-9897-4c585663f088.json`. Si no existen, `make db` y `uv run python -m search.freeze_run 285d1787-5d7c-464a-9897-4c585663f088` (la corrida está en tu Postgres local).
3. Pega este prompt al agente:

```text
Objetivo: que la demo dependa solo de archivos versionados de la corrida oficial
285d1787-5d7c-464a-9897-4c585663f088, para que Railway (viernes) vea lo mismo que local.

- Versiona bench/results/operator_card_285d1787-5d7c-464a-9897-4c585663f088.json y
  bench/results/replay_285d1787-5d7c-464a-9897-4c585663f088.json (ya los cubre la
  excepción de .gitignore; solo faltan en git).
- Añade a .gitignore la excepción !bench/results/efficiency_*.json y versiona
  bench/results/efficiency_20261015.json (la curva de la tabla oficial de GPU 4).
- Config: REPLAY_JOB_ID default = 285d1787-5d7c-464a-9897-4c585663f088 en Settings y
  .env.example. Los archivos de c43bd2f0 se quedan como histórico, no como default.
- Test: el operator_card de 285d1787 carga y su numbers contiene el % a tiempo
  holdout de la regla fija (≈0.506) y de la mejor política (≈0.988).
No hagas: re-correr búsquedas, baselines, ni eval.efficiency. No GPU.
Aceptación: ruff/pytest verdes; commit "demo: versiona la corrida oficial 285d1787".
```

## Cómo usar los prompts

Uno por uno. Revisa el diff y corre `uv run ruff check .`, `uv run ruff format --check .` y `uv run pytest -q` antes de cada commit. Un commit por prompt. Ningún número a mano en UI ni docs.

### Alcance actual (pegar en el archivo de contexto)

```markdown
## Alcance actual (jueves 15)
Hoy es solo UI/UX. Sin GPU. Sin re-correr búsquedas ni baselines.
Fuente de la demo: job 285d1787-5d7c-464a-9897-4c585663f088 (vLLM real Qwen3-8B,
planta calibrada). operator_card_285d1787-…json, replay_285d1787-…json,
bench/results/efficiency_20261015.json. % a tiempo holdout 50.6% → 98.8%.
guard/numbers.py verifica el texto de la tarjeta contra operator_card["numbers"].
UI de solo lectura: tarjeta de operador primero (% a tiempo, no objetivo compuesto),
aprobar/rechazar, curva Chart.js, badge REPLAY. MODE=replay sin LLM ni simulador.
Railway queda para el viernes.
No implementar: SSE, auth, premio Google, docker compose, fine-tuning, código generado
por el LLM, panel de hardware en vivo (captura OK).
```

---

## Prompt 21: guard/numbers + texto de la tarjeta

```text
Objetivo: ningún número del texto de la tarjeta se escribe a mano. Todo sale del
mapa plano operator_card["numbers"] de la corrida 285d1787-5d7c-464a-9897-4c585663f088.

Archivos:
- guard/numbers.py:
  - extract_numbers(text) -> set[str] de literales numéricos (enteros, decimales,
    porcentajes como "50.6%", "98.8%").
  - verify(text, numbers: dict[str, float], *, rtol=1e-4) -> list[str] de hallazgos.
    Cada número del texto coincide con algún valor de numbers (o value*100 si el
    texto usa porcentaje, aceptando redondeo a 1 decimal). Un número que no está en
    numbers es error.
  - render_card(card: dict) -> dict con headline, body, numbers_used, stress_caveat.
    El headline usa % a tiempo holdout (regla fija vs mejor política), NUNCA el
    objetivo compuesto. El body menciona la política ganadora, número de PM y la
    nota de estrés sin inventar cifras.
- En MODE=replay el camino es render_card determinista, sin LLM. Un camino con LLM,
  si existe, solo en live y siempre pasa por verify.
- tests/test_guard_numbers.py:
  - texto con un número inventado ("85% a tiempo") falla.
  - texto armado solo con numbers de la tarjeta 285d1787 pasa.
  - porcentajes redondeados a 1 decimal aceptados.
- docs/REPLAY.md: una línea de que el texto de UI pasa por guard/numbers.
No hagas: HTML, cambiar el schema de la tarjeta, re-simular.
Aceptación: ruff/pytest verdes; commit "prompt 21: guard numbers and card text".
```

---

## Prompt 22: UI tarjeta de operador (prioridad #1)

```text
Objetivo: la pantalla principal es la tarjeta de operador de la corrida oficial
285d1787. En MODE=replay no se llama al LLM ni al simulador.

Archivos:
- api/main.py (y módulos bajo api/ o ui/):
  - GET / : tarjeta de operador como vista principal, leyendo
    operator_card_{REPLAY_JOB_ID}.json del disco (no depender de Postgres en replay).
  - GET /api/replay/{job_id} para el JSON de replay.
  - POST /policies/{id}/approve y /policies/{id}/reject con body opcional {reason}.
    Persistir en DB si hay tabla; si no, archivo o memoria con test. Requiere
    ADMIN_TOKEN en header si Settings.ADMIN_TOKEN no está vacío.
  - Seguir sirviendo /healthz y /readyz.
- ui/templates/:
  - base.html mínimo (HTML limpio + poco CSS, sin framework pesado).
  - operator.html: titular % a tiempo regla fija → mejor política (de numbers),
    IC del objetivo como texto secundario, política ganadora, nota de estrés,
    botones Aprobar / Rechazar (HTMX POST, swap del estado). Badge grande REPLAY
    cuando MODE=replay. Una línea visible: "vLLM real (Qwen3-8B), planta calibrada".
  - El texto visible sale de render_card + verify; si verify falla, se muestra el
    error y no el texto.
- tests: GET / en MODE=replay contiene "REPLAY" y un porcentaje; POST approve sin
  token falla si ADMIN_TOKEN está seteado; con token responde 200.
No hagas: Chart.js (Prompt 23), Railway, SSE, auth de usuarios, panel GPU, animación 2D.
Aceptación: make web con MODE=replay muestra la tarjeta; ruff/pytest verdes;
commit "prompt 22: operator card ui".
```

---

## Prompt 23: curva Chart.js y comparación

```text
Objetivo: bajo la tarjeta, la curva de eficiencia de los cuatro métodos y una tabla
corta. Datos solo de JSON ya medidos.

Archivos:
- GET /api/efficiency que sirva bench/results/efficiency_20261015.json (la tabla
  oficial de GPU 4, planta calibrada). No usar efficiency_20261014.json (planta vieja).
- ui/templates/operator.html (o partial): sección "Eficiencia" con Chart.js (CDN).
  Eje x = simulaciones, y = mejor objetivo hasta ahí, una serie por método y una
  línea horizontal del umbral del 90% que trae el JSON.
- Tabla HTML: método | train | holdout | IC 95% | % a tiempo holdout | sims | sims al
  90% | fuente. Números solo del JSON; si falta un valor, celda "—".
- Párrafo fijo de honestidad, tomado de "Lo que hay que decir en cualquier
  presentación" en docs/PENDIENTES_JUEVES.md: el bucle y el one-shot son vLLM real;
  Optuna sigue arriba en objetivo compuesto; el bucle le gana al one-shot y entrega
  el salto de % a tiempo; el objetivo compuesto no se compara entre plantas; la
  calibración es de forma con un dataset público.
- tests: /api/efficiency responde 200 con las claves esperadas; la página incluye el
  canvas de la curva.
No hagas: re-correr eval.efficiency, panel hardware, Railway.
Aceptación: en el browser se ve la curva bajo la tarjeta; commit
"prompt 23: efficiency chart".
```

---

## Prompt 24: MODE=replay end-to-end

```text
Objetivo: una sola variable MODE=replay deja la demo usable con GPU apagada, y en
una máquina limpia (lo que verá Railway) solo con archivos versionados.

- .env.example y README: MODE=replay, REPLAY_JOB_ID=285d1787-5d7c-464a-9897-4c585663f088.
- En MODE=replay, cualquier ruta que encole búsqueda o hable con el LLM responde 503
  {"error":"replay_only"} (excepto healthz/readyz y lectura).
- README, sección "Demo en replay":
  cp .env.example .env  # MODE=replay
  make setup && make db
  make web
  Abrir http://localhost:8000/ y ver la tarjeta.
- docs/REPLAY.md: checklist de demo de 5 líneas.
- tests: con MODE=replay, POST /jobs (si existe) da 503; GET / da 200; la app arranca
  sin Postgres poblado si la tarjeta está en disco.
No hagas: deploy a Railway (viernes), SSE, Google prize.
Aceptación: probado con make web; commit "prompt 24: replay mode demo path".
```

---

## Opcional A: las 34 inválidas de la ronda 2 (sin GPU)

```text
Objetivo: entender por qué la ronda 2 del job 285d1787 dio 34 propuestas inválidas
(casi todas rules.*.if con condición vacía: machine y product_waiting nulos).
Revisa el prompt de search/prompts.py, policy/schema.py y el postproceso. Propón el
arreglo mínimo (normalizar o descartar condiciones vacías antes de validar, o aclarar
el schema en el prompt) con tests contra ejemplos reales del job.
No re-corras el bucle ni cambies los números oficiales de BENCHMARKS.
Commit "search: condiciones vacías en reglas".
```

## Opcional B: prerequisito de animación 2D

Según `2D-ANIMATION.md`: añadir `record: list | None = None` a `run_simulation` y un entrypoint que corra **una semilla y dos políticas** (regla fija y la ganadora de 285d1787) y escriba JSON estático `(machine, start, end, kind)` versionado en `bench/results/`. Nunca dentro del bucle de búsqueda. La pieza visual Gantt queda para el viernes.

---

## Checklist de cierre (~21:30)

- [ ] Artefactos de 285d1787 y `efficiency_20261015.json` en `main`.
- [ ] `guard/numbers.py` con tests; texto de tarjeta verificado.
- [ ] UI: tarjeta de operador + aprobar/rechazar + badge REPLAY.
- [ ] Curva Chart.js + tabla de cuatro métodos.
- [ ] `MODE=replay` bloquea mutaciones; README con camino de demo.
- [ ] Sin `.env` ni claves en git; ruff y pytest verdes; push a `main`.
- [ ] `docs/PENDIENTES_VIERNES.md` escrito.

### Prompt de cierre: `docs/PENDIENTES_VIERNES.md`

```text
Escribe docs/PENDIENTES_VIERNES.md con el estado real de hoy (commits y números, no
inventes) y, en orden:
1. Railway: web + Postgres administrado, MODE=replay, REPLAY_JOB_ID=285d1787-…,
   healthcheck /healthz, deploy desde main.
2. README probado en máquina limpia (o checklist honesto de lo no probado).
3. Panel de hardware: captura estática de rocm-smi / tokens-s de las sesiones GPU.
4. Animación 2D (Gantt) si el JSON de intervalos ya existe; si no, el prerequisito.
5. Guion de video de 3 min (tarjeta al centro) y portada 16:9.
6. Pitch deck en Netlify con botón "Ver en vivo" hacia la URL de Railway.
No tocar: fine-tuning, SSE salvo que sobre tiempo, premio Google si no hubo
respuesta de Discord.
Commit y push.
```
