# Sesión GPU 2: vLLM real, comparación por calidad

El mock no lee el prompt, así que no puede decir nada sobre el aporte del bucle. Esta sesión
mide contra vLLM de verdad: **el 8B contra el 32B por calidad de política** (objetivo en
semillas que la búsqueda no vio, misma N/K/R) y el LLM sin retroalimentación contra vLLM, que
es la comparación que el miércoles quedó pendiente.

Reparto de trabajo: **la GPU solo sirve vLLM**. Las simulaciones corren en la laptop con 16
workers y el acceso al modelo es por túnel SSH a `localhost:8000`.

Todo el manejo de la GPU va por `infra/gpu/gpu.sh`. Nunca dejar un `ssh -L` bloqueando la
terminal.

## Antes de empezar

```bash
# 1. Instancia MI300X x1 bajo demanda, imagen vLLM 0.27.1 1-Click. Anota IP, precio y hora.
# 2. Túnel en segundo plano (no bloquea la terminal) y vLLM arriba:
GPU_IP=<nueva> infra/gpu/gpu.sh tunnel
infra/gpu/gpu.sh serve Qwen/Qwen3-8B
infra/gpu/gpu.sh wait
infra/gpu/gpu.sh status

# 3. En la laptop: la api-key de la sesión y el mock apagado.
export LLM_API_KEY=<la del /root/vllm.key de la instancia>
pkill -f mock_server
```

Comprobaciones que hace `make gpu2` sola, antes de gastar 20 minutos: que `LLM_API_KEY` esté
puesta, que el mock no siga arriba y que `/v1/models` responda por el túnel.

Postgres local tiene que estar arriba (`make db`): el bucle se persiste ahí y de ahí sale el
replay.

## El comando

```bash
make gpu2
```

Con los valores por defecto: perfil `default` (N=48, K=180, R=8), `seed 1`, `holdout 300`,
16 workers, `Qwen/Qwen3-8B` y el túnel en `http://127.0.0.1:8000/v1`. Se pueden cambiar:

```bash
make gpu2 GPU2_SEED=2
make gpu2 GPU2_MODEL=Qwen/Qwen3-32B
```

Lo que corre, en orden:

1. **El bucle, vía worker** (para que holdout y estrés queden en Postgres):
   ```bash
   uv run python -m worker.enqueue search --profile default --seed 1 --scenario base --holdout 300
   SIM_WORKERS=16 uv run python -m worker.main --drain
   ```
   `--drain` procesa la cola y sale; sin él el worker se queda escuchando y hay que matarlo a
   mano. Las 300 semillas de holdout traen también el estrés, que se evalúa en las mismas
   semillas.
2. **El LLM sin retroalimentación**, mismo presupuesto y mismas semillas:
   ```bash
   uv run python -m baselines.llm_nofeedback --profile default --seed 1
   ```
3. **La tabla de los cuatro métodos**, con el replay congelado como fuente del bucle:
   ```bash
   uv run python -m search.freeze_run <job_id>
   uv run python -m eval.efficiency --profile default --seed 1 --workers 16 \
       --loop-json bench/results/replay_<job_id>.json --require-llm-source vllm
   ```

`--require-llm-source vllm` es el guardarraíl: si alguna corrida salió contra el mock (túnel
caído, `LLM_BASE_URL` en el 8001), **aborta** en vez de dejar una tabla con pinta de medida
real. El mensaje dice qué métodos y qué fuente declararon:

```
se esperaba llm_source='vllm' en los métodos que dependen del LLM y estos declaran otra cosa:
{'LLM sin retroalimentación': 'mock', 'bucle con retroalimentación': 'mock'}
```

La fuente no es una bandera escrita a mano: cada JSON la declara en `config.llm_source`, y
`search/repro.py` la deriva del endpoint (loopback **más** el puerto del mock, 8001; el túnel
va por el 8000).

## Qué deja

- `bench/results/replay_<job_id>.json` y `bench/results/operator_card_<job_id>.json`: la
  corrida congelada y la tarjeta. Se versionan.
- `bench/results/llm_nofeedback_default_seed1_<fecha>.json`: el one-shot.
- `bench/results/efficiency_<fecha>.json` y la tabla impresa en pantalla.

El número que decide el 8B contra el 32B es `numbers.objective_best_holdout` y
`numbers.on_time_rate_best_holdout` de la tarjeta de cada corrida: el objetivo de la mejor
política en semillas que la búsqueda no vio. No es tokens por segundo.

## 8B contra 32B

El one-shot y la tabla se escriben con el mismo nombre de archivo para el mismo perfil y
semilla, así que la segunda corrida pisa la primera. Aparta los del 8B antes de cambiar de
modelo:

```bash
mkdir -p bench/results/gpu2-8b
cp bench/results/llm_nofeedback_default_seed1_*.json bench/results/efficiency_*.json bench/results/gpu2-8b/
rm bench/results/llm_nofeedback_default_seed1_*.json

infra/gpu/gpu.sh serve Qwen/Qwen3-32B
infra/gpu/gpu.sh wait
make gpu2 GPU2_MODEL=Qwen/Qwen3-32B
```

Los `replay_*` y `operator_card_*` no chocan: llevan el `job_id` en el nombre. `bench/results`
está en `.gitignore` salvo esos dos patrones, así que las copias no ensucian el repo.

## Validación contra el mock (sin GPU)

El flujo entero se probó con el perfil `smoke` y el mock, que es rápido (segundos) y ejercita
los mismos pasos:

```bash
job=$(uv run python -m worker.enqueue search --profile smoke --seed 1 --scenario base --holdout 2)
SIM_WORKERS=4 uv run python -m worker.main --drain
uv run python -m baselines.llm_nofeedback --profile smoke --seed 1
uv run python -m baselines.optuna_search --profile smoke --seed 1
uv run python -m search.freeze_run "$job" --out /tmp/gpu2-smoke
uv run python -m eval.efficiency --profile smoke --seed 1 --workers 4 \
    --loop-json /tmp/gpu2-smoke/replay_$job.json --require-llm-source mock
```

Resultado observado: los cuatro métodos en la tabla, con el bucle y el one-shot marcados
`mock, no es medida del LLM`, y salida 0. Con `--require-llm-source vllm` la misma orden
**aborta con salida 1** nombrando los dos métodos, que es lo que tiene que pasar cuando el
túnel no está levantado.

Dos notas de la validación:

- El mock deja `LLM_BASE_URL` en el 8001; la sesión de GPU lo pone en el 8000. La diferencia
  de puerto es justo lo que distingue `mock` de `vllm`.
- `eval.efficiency` acepta como fuente del bucle tanto el JSON de `search.loop` como un
  `replay_*` congelado. Hace falta porque en esta sesión el bucle corre por el worker y no
  escribe el JSON de `search.loop`.

## Al terminar

```bash
infra/gpu/gpu.sh stop
infra/gpu/gpu.sh untunnel
# Destruir la instancia en la consola y anotar hora de fin y costo.
```

El 8B sigue como `LLM_MODEL` por defecto hasta que la comparación de holdout diga otra cosa.
