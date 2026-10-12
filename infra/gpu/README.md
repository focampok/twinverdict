# Sesión GPU (AMD Developer Cloud, MI300X)

1. Crear la instancia en la consola. Anotar el precio por hora y la hora de inicio antes de confirmar.
2. `ssh` a la instancia, copiar `infra/gpu/.env.gpu` (nunca al repo), ejecutar `./infra/gpu/up.sh` y después `./infra/gpu/vllm.sh start`.
3. Túnel desde Linux local: `ssh -N -L 8000:127.0.0.1:8000 usuario@IP`. vLLM queda en `http://127.0.0.1:8000/v1` y no se expone a internet.
4. Benchmarks del harness (`bench.llm_smoke`, `bench.llm_throughput`, `bench.sim_speed`, `bench.budget`).
5. Cierre: copiar resultados (`scp` de `docs/BENCHMARKS.md` o `git push`), `./infra/gpu/vllm.sh stop`, y destruir la instancia en la consola. Apagarla no basta: puede seguir cobrando. Anotar hora de fin y costo estimado.
