# Pendientes del viernes 16

Hecho el jueves, en `main`. Corrida oficial: job `285d1787-5d7c-464a-9897-4c585663f088`,
vLLM real `Qwen/Qwen3-8B`, planta calibrada (`failure_midpoint` 0.95, `failure_steepness` 18).
Titular de la tarjeta: **50.6% → 98.8%** a tiempo en holdout (300 semillas). Tabla en
`docs/BENCHMARKS.md` (GPU 4) y en `bench/results/efficiency_20261015.json`: regla fija
0.7725 / 50.6% (180 sims), Optuna 1.5126 / 99.9% (69_300), one-shot 1.2259 / 91.4%
(69_300), bucle 1.3863 / 98.8% (48_540). Optuna sigue arriba en objetivo compuesto
(train 1.5188 frente a 1.3810 del bucle). El bucle no cruza el umbral 1.4455.

Commits del jueves, del más nuevo al cierre de la UI:

- `ab01ff6` ui: badge «Recorded run · real vLLM (Qwen3-8B on MI300X)» y texto visible de la app en inglés. CI [38831381652](https://github.com/focampok/twinverdict/actions/runs/38831381652) verde. `MODE=replay` no cambió.
- `264a3ac` visual: página estática del Gantt en `netlify-visual/`.
- `59d1122` sim: intervalos del holdout (semillas 1000104, 1000111, 1000176).
- `ea26dd1` prompt 24: camino de demo en `MODE=replay`.
- `1ffb083` prompt 23: curva de eficiencia.
- `45184cc` prompt 22: tarjeta de operador.
- `1f8ad07` prompt 21: `guard/numbers.py`.
- `467ec8c` demo: versiona la corrida 285d1787 y `efficiency_20261015.json`.

`railway.toml` ya tiene `healthcheckPath = "/healthz"` y arranque con `alembic` + uvicorn.
No hay servicio Railway creado ni URL pública.

## En orden

1. **Railway.** Web + Postgres administrado, `DATABASE_URL` referenciada, `MODE=replay`,
   `REPLAY_JOB_ID=285d1787-5d7c-464a-9897-4c585663f088`, healthcheck `/healthz`, deploy
   desde `main`. Hoy no está desplegado. Si el deploy falla, el plan B del viernes por
   la noche es cualquier hosting del modo replay; no se pierde el sábado en infraestructura.

2. **README en máquina limpia.** El camino está escrito (`cp .env.example .env`,
   `make setup && make db`, `make web`, http://localhost:8000/). En esta máquina se vio
   la tarjeta y `POST /jobs` respondió 503 `replay_only`. **No se probó en una máquina
   limpia.** Checklist de lo no probado: clone fresco, Postgres vacío, sin `.env` previo,
   sin el venv de este repo.

3. **Panel de hardware.** No hay captura estática de `rocm-smi` ni de tokens/s en la UI.
   Las sesiones están narradas en `docs/BENCHMARKS.md` y `docs/SESION_GPU.md` /
   `docs/SESION_GPU2.md`. Mañana: una captura de esas sesiones, no un panel en vivo.

4. **Animación 2D.** El JSON ya existe: `netlify-visual/data/intervals_1000104.json`,
   `intervals_1000111.json` (semilla por defecto) e `intervals_1000176.json`. La página
   local (`index.html` + `gantt.js`) muestra los dos carriles, el playhead y el badge.
   Falta el clip de 10–12 s en 1080p y publicarla. No hace falta el prerequisito del
   simulador: `sim/record.py` ya está y no lo llama el bucle.

5. **Guion de 3 min y portada 16:9.** El esquema sigue en `docs/PLAN.md` (tarjeta al
   centro, 0:40). No hay guion cerrado ni portada. La tarjeta que se muestra es la
   captura en inglés de `netlify-visual/img/operator-card.png`.

6. **Pitch en Netlify.** La página está en `netlify-visual/` y no está publicada.
   El botón dice «See it live →», `RAILWAY_URL` está vacío y el aviso es «coming soon»
   hasta que exista la URL del punto 1.

## No tocar

- Fine-tuning.
- SSE, salvo que sobre tiempo después del deploy.
- Premio de Google: no hay respuesta de Discord registrada en el repo. No se agrega nada de Google.
- Las 34 reglas inválidas de la ronda 2 del job 285d1787 (38 inválidas en total, 262 válidas). No bloquean la demo. No re-correr el bucle ni cambiar los números de `docs/BENCHMARKS.md`.
