# TwinVerdict: prompts del viernes 16 oct (deploy + entrega)

Fuente: `docs/PENDIENTES_VIERNES.md`. Corrida oficial actual:
`c0c92625-de22-4520-accb-6a17c1a76428` (vLLM real Qwen3-8B en MI300X, con telemetría).

Holdout a tiempo **50.6% → 98.9%**; bucle 1.3691 [1.3530, 1.3842], 37_560 sims
(`efficiency_20261017.json`). Optuna sigue arriba en objetivo compuesto.

## Agenda

| Hora (GT) | Paso | Prioridad |
|---|---|---|
| 09:00 a 10:30 | Paso 1: Railway (web + Postgres, MODE=replay) | Obligatorio |
| 10:30 a 11:15 | Paso 2: README en máquina limpia (checklist) | Obligatorio |
| 11:15 a 12:00 | Paso 3: captura hardware estática + meterla en Netlify/UI | Obligatorio |
| 12:00 a 13:00 | Comida | |
| 13:00 a 14:30 | Paso 4: publicar Netlify + cablear RAILWAY_URL | Obligatorio |
| 14:30 a 16:00 | Paso 5: clip Gantt 10–12 s 1080p | Obligatorio |
| 16:00 a 17:30 | Paso 6: guion cerrado + portada 16:9 | Obligatorio |
| 17:30 a 19:00 | Paso 7: grabar video 3 min (o ensayo sólido) | Obligatorio |
| 19:00 a 20:00 | Margen / plan B hosting si Railway falló | Contingencia |

Recorte si no da: Railway + Netlify con «See it live» + tarjeta en video. El clip Gantt
y la captura de hardware son nice-to-have frente a URL viva + guion.

## Alcance (pegar en el contexto del agente)

```markdown
## Alcance actual (viernes 16)
Deploy y empaque de entrega. Sin GPU de búsqueda. Sin re-correr baselines.
Demo: MODE=replay, REPLAY_JOB_ID=c0c92625-de22-4520-accb-6a17c1a76428.
UI y visuals en inglés. Números solo de operator_card / efficiency JSON.
railway.toml ya tiene healthcheck /healthz y alembic + uvicorn.
No tocar: fine-tuning, SSE (salvo tiempo sobrante), premio Google, re-medir BENCHMARKS,
arreglar las 34 reglas inválidas de la ronda 2.
```

---

## Paso 1: Railway (tú en el dashboard; el agente solo verifica el repo)

Hecho en repo: `railway.toml` con `healthcheckPath = "/healthz"`,
`startCommand = "alembic upgrade head && uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"`,
Dockerfile de deploy.

Checklist manual:

1. Nuevo proyecto Railway desde `focampok/twinverdict` rama `main`.
2. Add Postgres. `DATABASE_URL` = `${{Postgres.DATABASE_URL}}` (o la forma que Railway
   dé para el servicio Postgres del mismo proyecto).
3. Variables: `MODE=replay`,
   `REPLAY_JOB_ID=c0c92625-de22-4520-accb-6a17c1a76428`,
   `LLM_API_KEY=mock` (no se llama LLM en replay), `ADMIN_TOKEN=` vacío o un token
   fuerte si quieres probar approve.
4. Deploy. Abrir `/healthz` → 200. Abrir `/` → tarjeta en inglés, badge
   «Recorded run · real vLLM», 50.6% → 98.9%.
5. `POST /jobs` (si existe) → 503 `replay_only`.
6. Anota la URL pública (https://….up.railway.app o dominio).

Plan B (noche): cualquier hosting estático/contenedor del modo replay; no quemar el
sábado en infraestructura. La tarjeta y el Gantt viven en `netlify-visual/` aunque
Railway falle.

Si el agente debe dejar el repo listo para variables documentadas:

```text
Objetivo: documentar el deploy Railway sin tocar números ni re-correr nada.

- README: sección "Deploy (Railway)" con MODE=replay, REPLAY_JOB_ID=c0c92625-…,
  DATABASE_URL, healthcheck /healthz, y que POST de búsqueda responde 503.
- Confirma que .env.example ya trae esos defaults (no inventes otros job ids).
- No crees el servicio Railway desde CI; solo docs.
Aceptación: ruff/pytest verdes si tocaste código; commit
"docs: railway replay deploy checklist".
```

---

## Paso 2: README en máquina limpia

```text
Objetivo: checklist honesto de lo no probado en máquina limpia.

En docs/REPLAY.md o README, marca explícito:
- Probado aquí: make web + tarjeta + POST /jobs → 503 replay_only.
- No probado aún: clone fresco, Postgres vacío, sin .env previo, sin venv del repo.

Si puedes, corre en un directorio /tmp el camino:
  git clone … && cd twinverdict && cp .env.example .env
  make setup && make db && make web
y anota el resultado real (pasa / falla + error).
No hagas: GPU, re-simular, cambiar REPLAY_JOB_ID.
Commit: "docs: clean-machine replay checklist".
```

---

## Paso 3: panel de hardware (captura, no live)

```text
Objetivo: una captura estática de rocm-smi / tokens-s de SESION_GPU / SESION_GPU2
para la UI o netlify-visual/img/. No panel en vivo.

- Elige una captura ya narrada en docs/BENCHMARKS.md o docs/SESION_GPU*.md.
- Guárdala como netlify-visual/img/hardware.png (o similar) y enlázala desde
  index.html o la tarjeta con caption en inglés (ej. "MI300X · recorded session").
- Sin scrapear la droplet ahora; sin GPU encendida.
Commit: "docs: static hardware capture for pitch".
```

(Si no hay PNG a mano, saca uno de la narración de sesión o posponlo tras Netlify.)

---

## Paso 4: Netlify + cablear URL viva

```text
Objetivo: publicar netlify-visual/ y que «See it live →» apunte a Railway.

- Publicar la carpeta netlify-visual/ en Netlify (drag-drop o repo subdir).
- Sustituir RAILWAY_URL vacío por la URL del Paso 1.
- Quitar el aviso «coming soon» cuando la URL responda /healthz.
- Texto del botón ya en inglés («See it live →»); no volver a español.
- Verificar en móvil/desktop que operator-card.png y el Gantt cargan.
No hagas: reescribir el Gantt, cambiar números de la tarjeta.
Commit si el URL queda en el repo: "visual: wire live Railway URL".
```

---

## Paso 5: clip Gantt 10–12 s

Hecho: `netlify-visual/data/intervals_*.json`, `index.html`, `gantt.js`,
semilla default 1000111. Falta grabar 1080p (OBS/browser) 10–12 s con playhead.

No hace falta prompt de código salvo un `README` de un párrafo en `netlify-visual/`
con «open index.html / published URL, record 10–12 s at 1080p, seed 1000111».

---

## Paso 6: guion 3 min + portada 16:9

Esquema PLAN.md (tarjeta al centro). Guion de voz en inglés (jurado). Borrador listo
en `amd-hackathon-act-iii/guion-video-3min-en.md` (mismo directorio que estos prompts).

Portada 16:9: título TwinVerdict, subtítulo una línea del salto 50.6% → 98.9%, badge
AMD / vLLM / MI300X, sin inventar métricas.

```text
Objetivo: cerrar docs/VIDEO.md (o similar) con el guion en inglés y checklist de
portada. Números solo de operator_card / BENCHMARKS. Commit
"docs: 3-min video script and cover checklist".
```

---

## Paso 7: grabar

Ensayo con `make web` local o URL Railway. Orden del guion. Export MP4. Dejar margen
para el sábado (polish + submit lablab; deadline dom 18 oct 09:00 GT).

## Sesión GPU5: grabar el «Live run»

Objetivo: una corrida completa del bucle con telemetría grabada, para que `/live` la
reproduzca en replay con el badge «Recorded run · real vLLM on MI300X». Mismo reparto que
GPU2: la GPU solo sirve vLLM, las simulaciones corren en la laptop.

Qué graba el worker (`worker/telemetry.py`), cada 2 s, en `data/replay/live_<job_id>.json`:
`/metrics` de vLLM (tokens generados → tokens/s, peticiones en curso), el id de
`/v1/models`, `infra/gpu/gpu.sh smi` (rocm-smi: uso %, VRAM %, potencia W, nombre) y el
progreso del bucle (ronda, propuestas válidas/inválidas/duplicadas, simulaciones, mejor
objetivo). Solo graba con `MODE=live` y un `LLM_BASE_URL` que no sea el mock. Si rocm-smi o
`/metrics` fallan, ese evento lleva null y el job sigue. La api-key no se escribe en el JSON.

```bash
# 1. Panel de DigitalOcean: GPU Droplet MI300X x1, imagen vLLM 1-Click, nombre
#    twinverdict-gpu5. Anota IP, precio y hora de arranque.
export GPU_IP=<ip de twinverdict-gpu5>

# 2. vLLM y túnel (gpu.sh smi reusa la conexión del túnel).
infra/gpu/gpu.sh tunnel
infra/gpu/gpu.sh serve Qwen/Qwen3-8B
infra/gpu/gpu.sh wait
infra/gpu/gpu.sh status
infra/gpu/gpu.sh smi | head -c 400; echo   # tiene que ser JSON con card0

# 3. Laptop: la api-key en .env (LLM_API_KEY=<la de /root/vllm.key>), nunca en el repo.
#    El mock apagado.
pkill -f mock_server || true
make db

# 4. Job completo con grabación. MODE=live va en la línea de make: el Makefile incluye .env
#    (MODE=replay) y eso pisaría un export del shell. El worker imprime
#    "telemetry -> data/replay/live_<job>.json" al empezar.
make gpu2 MODE=live
#    En otra terminal, opcional (el túnel ocupa el 8000):
#    MODE=live uv run uvicorn api.main:app --port 8010  →  http://localhost:8010/live

# 5. Revisar la grabación: fake=false, status=done, eventos con gpu y vllm no nulos.
uv run python -c "import json,sys; d=json.load(open(sys.argv[1])); \
print(d['fake'], d['status'], len(d['events']), d['model'], d['gpu_name'])" \
  data/replay/live_<job>.json

# 6. Al repo: la grabación, y el replay/tarjeta de ese job si pasa a ser la demo.
#    Si el job nuevo reemplaza a 285d1787, apunta REPLAY_JOB_ID en .env.example,
#    config.py y Railway. Si no, la grabación sirve solo si es del job de REPLAY_JOB_ID.
git add data/replay/live_<job>.json
git commit -m "data: live run telemetry from GPU5"

# 7. Apagar: túnel, vLLM y destruir twinverdict-gpu5 en el panel. Anota la hora.
infra/gpu/gpu.sh stop
infra/gpu/gpu.sh untunnel
```

Mientras no exista la grabación real, `uv run python -m worker.telemetry --fake` escribe
`data/replay/live_<REPLAY_JOB_ID>.fake.json` con `fake=true`. Está en `.gitignore`: no se
versiona y la UI la muestra con «Test recording · fake data», nunca con el badge real.

## No tocar

Fine-tuning · SSE salvo sobra · Google prize · re-correr bucle · cambiar BENCHMARKS ·
arreglar las 34 inválidas de ronda 2.
