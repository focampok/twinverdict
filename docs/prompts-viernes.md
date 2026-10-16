# TwinVerdict: prompts del viernes 16 oct (deploy + entrega)

Fuente: `docs/PENDIENTES_VIERNES.md` en `main` tip `da83aac` (jue 15, ~18:48 GT).
Jueves cerrado: tarjeta EN, badge «Recorded run · real vLLM», Gantt en `netlify-visual/`,
`MODE=replay` con job `285d1787-5d7c-464a-9897-4c585663f088`. CI verde en ab01ff6.

Corrida oficial (no re-medir): holdout a tiempo **50.6% → 98.8%**. Optuna sigue arriba
en objetivo compuesto. Sin GPU mañana salvo captura estática ya narrada.

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
Demo: MODE=replay, REPLAY_JOB_ID=285d1787-5d7c-464a-9897-4c585663f088.
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
   `REPLAY_JOB_ID=285d1787-5d7c-464a-9897-4c585663f088`,
   `LLM_API_KEY=mock` (no se llama LLM en replay), `ADMIN_TOKEN=` vacío o un token
   fuerte si quieres probar approve.
4. Deploy. Abrir `/healthz` → 200. Abrir `/` → tarjeta en inglés, badge
   «Recorded run · real vLLM», 50.6% → 98.8%.
5. `POST /jobs` (si existe) → 503 `replay_only`.
6. Anota la URL pública (https://….up.railway.app o dominio).

Plan B (noche): cualquier hosting estático/contenedor del modo replay; no quemar el
sábado en infraestructura. La tarjeta y el Gantt viven en `netlify-visual/` aunque
Railway falle.

Si el agente debe dejar el repo listo para variables documentadas:

```text
Objetivo: documentar el deploy Railway sin tocar números ni re-correr nada.

- README: sección "Deploy (Railway)" con MODE=replay, REPLAY_JOB_ID=285d1787-…,
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

Portada 16:9: título TwinVerdict, subtítulo una línea del salto 50.6% → 98.8%, badge
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

## No tocar

Fine-tuning · SSE salvo sobra · Google prize · re-correr bucle · cambiar BENCHMARKS ·
arreglar las 34 inválidas de ronda 2.
