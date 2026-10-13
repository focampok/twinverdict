# Sesión GPU (martes 13 oct 2026)

Ritual de la sesión con la MI300X ya creada. Precio de esta sesión: **$1.99/h**
(escenario A del plan, unas 50 h con $100). No improvisar con el reloj corriendo.
No crear ni destruir la instancia desde el repo: la consola es el único lugar
donde se crea y se destruye.

## Lo que corre hoy

- Imagen: **DigitalOcean vLLM 0.27.1 1-Click**. No es el contenedor que arma
  `infra/gpu/vllm.sh` (ese script crea un contenedor `vllm` en `127.0.0.1`).
- Contenedor: **`rocm`**.
- vLLM se lanza con **`docker exec`** dentro de `rocm`, con **`--api-key`**.
  Modelo de esta sesión: `Qwen/Qwen3-8B`.
- Docker publica el puerto **8000 en `0.0.0.0`**. Por eso la api-key es
  obligatoria: el puerto no queda solo en localhost.
- Desde la laptop el acceso es el **túnel SSH**. `LLM_BASE_URL` local es
  `http://127.0.0.1:8000/v1`. La clave vive en `.env` (gitignored) y no se
  imprime ni se commitea.
- Al terminar la sesión la instancia se **destruye** en la consola. Apagarla
  puede seguir cobrando.

## Checklist

1. Anotar el precio por hora de la consola ($1.99), la hora de inicio y el
   escenario A (~50 h a $1.99).
2. Crear la instancia con la imagen 1-Click DigitalOcean vLLM 0.27.1. Anotar
   IP y usuario SSH. Sin Terraform y sin la API de DigitalOcean.
3. Confirmar el contenedor `rocm`. Lanzar vLLM con `docker exec` y `--api-key`
   (modelo `Qwen/Qwen3-8B`). No quitar la clave: el puerto 8000 está publicado
   en `0.0.0.0`.
4. Túnel desde Linux: `ssh -N -L 8000:127.0.0.1:8000 usuario@IP`. En `.env`
   local: `LLM_BASE_URL=http://127.0.0.1:8000/v1`, `LLM_MODEL=Qwen/Qwen3-8B`,
   `LLM_API_KEY` igual que `--api-key`. Comprobar `GET /v1/models` por el
   túnel. No abrir el puerto en el navegador ni pegar la clave en el repo.
5. Smoke de JSON guiado con el esquema de `policy/schema.py`:
   `uv run python -m bench.llm_smoke --n 20`. Si la tasa de válidas es menor
   que 0.95, leer los logs del contenedor `rocm` y ajustar o cambiar de modelo.
6. Throughput: `uv run python -m bench.llm_throughput --concurrency 1,8,32 --n 64`.
   Anotar tokens/s, p50 y p95.
7. Un solo modelo en esta sesión (`Qwen/Qwen3-8B`). Elegir uno más grande solo
   si la tasa de válidas, la estabilidad del contenedor y los tokens/s lo
   justifican, y en otra ventana de GPU.
8. Segundos por simulación en la laptop (no en la GPU):
   `uv run python -m bench.sim_speed --seeds 100 --workers <nproc>`.
9. `GPU_PRICE_PER_HOUR=1.99 uv run python -m bench.budget`. Fijar `N`, `K` y
   `R` en `search/config.py` para que una búsqueda completa tarde 20 a 30 min.
10. Llenar `docs/BENCHMARKS.md`, sección "Martes 13, MI300X", con los números
    reales. Commit. No inventar cifras.
11. Parar vLLM. **Destruir** la instancia en la consola (no solo apagarla).
    Anotar hora de fin y costo (`horas × 1.99`).
