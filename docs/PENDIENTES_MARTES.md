# Pendientes del martes 13

Hecho el lunes contra el mock, no contra la GPU: `infra/gpu/` (shellcheck limpio), `bench.llm_smoke` 8/8 y `bench.llm_throughput` + `bench.budget`. Los defaults de búsqueda no se cambiaron.

En este orden:

1. Precio público anotado: MI300X a $2.59/hora bajo demanda, así que aplica la tabla de unas 38 horas del plan v4. El método de pago ya está en la cuenta. Al crear la instancia, confirma que la consola muestra ese mismo precio y anota la hora de inicio.
2. Crear la instancia, anotar hora de inicio y precio, copiar `.env.gpu` y correr `infra/gpu/up.sh` y `infra/gpu/vllm.sh start`.
3. vLLM con dos modelos y salida JSON guiada (`response_format` json_schema strict). Si un modelo escribe razonamiento antes del JSON, desactivarlo o cambiar de modelo.
4. Túnel SSH y smoke real (`bench.llm_smoke --n 32`), luego `bench.llm_throughput`. Repetir con el segundo modelo.
5. En la instancia: `bench.sim_speed --workers <nproc - 2>` y `bench.budget` con `GPU_PRICE_PER_HOUR`.
6. Fijar N, K y R en `search/config.py` con esos números, llenar la sección "Martes 13, MI300X" de `docs/BENCHMARKS.md`, commit y push.
7. `infra/gpu/vllm.sh stop` y destruir la instancia en la consola. Apagarla no basta.
8. Arrancar el bucle de búsqueda (primero en local contra el mock, luego en la instancia).
9. Revisar la versión mayor del Postgres de Railway. Local y `PG_MAJOR` del CI están en 16 (PostgreSQL 16.15). Igualarlos si Railway no es 16.
