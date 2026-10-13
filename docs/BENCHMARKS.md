# Benchmarks

Fecha de la medición local: 2026-10-12. Postgres local 16.15. Los números de la MI300X se llenan el martes.

Precio público de DigitalOcean, vigente al 12 oct 2026: AMD Instinct MI300X a $2.59/GPU/hora bajo demanda (1 GPU; 20 vCPU, 240 GiB RAM, 192 GB de memoria de GPU). El paquete de 8 GPUs son $20.72/hora. El plan reservado a 12 meses es $1.91/GPU/hora y no aplica a sesiones que se destruyen el mismo día. Con $100 de crédito, $2.59/hora da unas 38 horas: la tabla B del plan v4. Fuente: [GPU Droplets Pricing](https://www.digitalocean.com/pricing/gpu-droplets). El método de pago de la cuenta ya está agregado.

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

- Modelo: `Qwen/Qwen3-8B`.
- Imagen: DigitalOcean vLLM 0.27.1 1-Click. Contenedor e imagen Docker `rocm`. vLLM lanzado con `docker exec` y `--api-key`. Fingerprint del servidor: `vllm-0.27.1-71b87f10`.
- Núcleos de la instancia: 20 (`nproc`). La simulación de abajo no corrió ahí.
- Precio por hora de esta sesión: $1.99 (escenario A, unas 50 h con $100). Docker publica el puerto 8000 en `0.0.0.0`; la api-key es obligatoria. El acceso medido fue el túnel SSH a `127.0.0.1:8000`.
- `bench.llm_smoke --n 20` contra el esquema de `policy/schema.py` (`response_format` json_schema strict): 20/20 válidas, tasa 1.000. p50 4.372 s, p95 5.259 s, 570.1 tokens de salida por segundo. El cliente pide las 20 en paralelo (concurrencia 32).
- `bench.llm_throughput --concurrency 1,8,32 --n 64` (64/64 válidas en los tres niveles):

  | conc | válidas/min | tok/s | p50 s | p95 s |
  |---:|---:|---:|---:|---:|
  | 1 | 65.8 | 175.1 | 0.8731 | 1.6029 |
  | 8 | 310.5 | 821.4 | 1.3401 | 2.4921 |
  | 32 | 796.5 | 2267.5 | 1.8544 | 3.3896 |

- `bench.sim_speed --seeds 100 --workers 16` en esta laptop (16 núcleos, la misma del lunes): serie media 0.0909 s, p95 0.1137 s. Paralelo, tiempo dentro del proceso: media 0.1741 s, p95 0.2897 s. Reloj de pared: 1.206 s para 100 simulaciones, 0.0121 s por simulación.
- `bench.budget` con `GPU_PRICE_PER_HOUR`: pendiente del cierre de N, K y R.
- Combinación elegida (N, K, R): pendiente.
- Hora de inicio, hora de fin y costo de la sesión: la instancia sigue encendida. No se anota el cierre hasta destruirla en la consola.
