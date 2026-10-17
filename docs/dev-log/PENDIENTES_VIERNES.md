# Pendientes del viernes 16

Estado: corrida oficial `c0c92625-de22-4520-accb-6a17c1a76428` (vLLM real Qwen3-8B en
MI300X, con telemetría). Holdout (300 semillas): regla fija 0.7725 / **50.6%**,
Optuna 1.5126 / 99.9%, one-shot 1.2259 / 91.4%, bucle 1.3691 / **98.9%** (37_560 sims,
IC [1.3530, 1.3842]). Detalle en `docs/BENCHMARKS.md` y
`bench/results/efficiency_20261017.json`.
Hecho: guard de números, tarjeta, curva, replay, telemetría `/live`, Try a policy, Gantt.

## Orden nuevo (prompts en `docs/prompts-viernes.md`)

1. **Probador de políticas "Try a policy"** (~3 h, sin GPU): controles de regla, umbrales M1–M5,
   max_pm_per_shift; simula 20 semillas del holdout y compara usuario / regla fija / LLM c0c92625; Gantt.
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
