# Pendientes del viernes 16

Estado: `main` en `da83aac`, CI verde. Corrida oficial `285d1787-5d7c-464a-9897-4c585663f088`
(vLLM real Qwen3-8B, planta calibrada). Holdout (300 semillas): regla fija 0.7725 / **50.6%**,
Optuna 1.5126 / 99.9%, one-shot 1.2259 / 91.4%, bucle 1.3863 / **98.8%** (48_540 sims).
Detalle en `docs/BENCHMARKS.md` y `bench/results/efficiency_20261015.json`.
Hecho el jueves: guard de números, tarjeta del operador, curva, modo replay, grabador de intervalos,
Gantt en `netlify-visual/`, texto en inglés (`ab01ff6`).

## Orden nuevo (prompts en `docs/prompts-viernes.md`)

1. **Probador de políticas "Try a policy"** (~3 h, sin GPU): controles de regla, umbrales M1–M5,
   max_pm_per_shift; simula 20 semillas del holdout y compara usuario / regla fija / LLM 285d1787; Gantt.
2. **Prueba local completa + video**: README en clone limpio; GPU opcional con nombre nuevo
   (`twinverdict-gpu5`), captura de `rocm-smi` y tokens/s, y luego destruirla; grabar el video de 3:00 en inglés
   (clip del Gantt de 10–12 s, semilla 1000111).
3. **Producción**: crear el proyecto de Railway recién aquí (web desde Dockerfile + Postgres,
   `MODE=replay`, `REPLAY_JOB_ID`, `DATABASE_URL=${{Postgres.DATABASE_URL}}`, `ADMIN_TOKEN`,
   `SIM_WORKERS=2`), luego el dominio `twinverdict.focampo.com` (CNAME; DNS only si usas Cloudflare), luego
   `RAILWAY_URL` en `gantt.js` y el deploy en Netlify. Railway arriba a más tardar el viernes en la noche.

## Sábado 17
Tarde completa para el envío (lablab, video, README para jueces). El plazo vence el domingo 18 a las 09:00 (hora de Guatemala).

## No tocar
Fine-tuning, SSE, nada de Google, re-correr el bucle o cambiar BENCHMARKS. Las 34 inválidas de la ronda 2
quedan como opcional.
