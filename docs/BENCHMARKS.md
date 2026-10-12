# Benchmarks

Fecha de la medición local: 2026-10-12. Postgres local 16.15. Los números de GPU se llenan el martes; no hay precio por hora confirmado en la consola.

## Lunes 12, máquina local

- Hardware: Intel Core Ultra 7 255H, 16 núcleos, 1 hilo por núcleo, x86_64.
- Comando: `uv run python -m bench.sim_speed --seeds 100 --workers 16`.
- Serie: media 0.1038 s, p95 0.1386 s por simulación.
- Paralelo, tiempo dentro de cada proceso: media 0.1582 s, p95 0.2356 s.
- Paralelo, reloj de pared con 16 workers: 1.144 s para 100 simulaciones, 0.0114 s por simulación.
- Una búsqueda de K=100, N=32, R=8 (25_600 simulaciones) cabe en 4.88 min en estos 16 núcleos.
- En 25 min caben unas 131_000 simulaciones a ese ritmo.
- Un solo núcleo, al ritmo de la serie (0.1038 s), tardaría unos 44 min en esas 25_600 simulaciones.
- Para bajar de 25 min bastan unos 4 núcleos si el escalado se parece al medido (16 núcleos × 4.88 / 25 ≈ 3.1, redondeado hacia arriba).

El mock LLM en esta misma máquina (`bench.llm_throughput --concurrency 8,16,32,64 --n 64`) dio tasa de válidas 1.0. El mejor ritmo fue 16 en paralelo, unas 58_700 políticas válidas por minuto. Ese número es del mock, no de vLLM. `bench.budget` con `SIM_WORKERS=16` y sin `GPU_PRICE_PER_HOUR` recomienda N=48, K=100, R=8 en 7.44 min, pero los defaults de `search/config.py` siguen en N=32, K=100, R=8 hasta medir la MI300X. El mock no limita la búsqueda; la GPU sí puede hacerlo.

## Martes 13, MI300X

- Modelo:
- Imagen de vLLM (tag exacto):
- Núcleos de la instancia:
- Precio por hora confirmado en la consola:
- `bench.llm_smoke`:
- `bench.llm_throughput`:
- `bench.sim_speed` en la instancia:
- `bench.budget` con `GPU_PRICE_PER_HOUR`:
- Combinación elegida (N, K, R):
- Hora de inicio, hora de fin y costo de la sesión:
