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
- `bench.budget` con `GPU_PRICE_PER_HOUR=1.99`: la grilla del harness (N en 16/32/48, K en 30/50/100, R en 6/8) cabe entera en 25 min. La más grande es N=48, K=100, R=8 en 8.32 min (39_000 simulaciones, $0.28). Eso queda por debajo de la ventana de 20 a 30 min, así que K sube fuera de la grilla.
- Combinación elegida: **N=48, K=300, R=8** (23.8 min). Cálculo con 796.5 políticas válidas por minuto a concurrencia 32 y 0.012056 s por simulación (16 workers):
  - Propuestas: 48 × 8 = 384. Tiempo de LLM: 384 / 796.5 = 0.48 min.
  - Simulaciones: 48 × 300 × 8 = 115_200 de entrenamiento, más 300 reservadas y 300 de estrés = 115_800.
  - Tiempo de simulación: 115_800 × 0.012056 / 60 = 23.27 min.
  - Total: 0.48 + 23.27 = 23.8 min. Costo de GPU a $1.99/h: 23.8 / 60 × 1.99 = $0.79.
  - El reloj es la simulación. Subir K de 100 a 300 usa la ventana en más semillas por política. N=48 es el tope de la grilla; R=8 es el del plan. Con `SIM_WORKERS=2` el tramo de simulación se alarga ×8 y se sale de la ventana.
- Hora de inicio, hora de fin y costo de la sesión: la instancia ya fue destruida. El repo no tiene la hora de fin ni el costo cerrado.

## Qwen3-32B, misma sesión

Cambio con `infra/gpu/gpu.sh serve Qwen/Qwen3-32B` y `wait`, antes de destruir la instancia. El cliente manda `chat_template_kwargs.enable_thinking=false`: sin eso, una de 20 peticiones del 32B no terminaba (dos intentos, ~50 tokens/s sin parar). El 8B de arriba se midió con el thinking por defecto; el JSON guiado igual cerraba solo.

- `bench.llm_smoke --n 20`: 17/20 válidas, tasa 0.850. p50 1.598 s, p95 2.660 s, 425.0 tokens de salida por segundo. Las 3 inválidas traen `rule=WEIGHTED` sin `weights`; el esquema guiado los deja opcionales y Pydantic los exige.
- `bench.llm_throughput --concurrency 1,8,32 --n 64`:

  | conc | válidas/min | tok/s | p50 s | p95 s | válidas |
  |---:|---:|---:|---:|---:|---:|
  | 1 | 48.2 | 49.2 | 0.8762 | 1.8249 | 55/64 |
  | 8 | 275.5 | 281.2 | 1.1111 | 2.4059 | 56/64 |
  | 32 | 634.2 | 675.0 | 2.0813 | 3.7793 | 56/64 |

## Comparación 8B vs 32B

Misma laptop para la simulación (0.0121 s por simulación, 16 workers). Concurrencia 32:

| | 8B | 32B |
|---|---:|---:|
| JSON válido (smoke, n=20) | 100% | 85% |
| válidas/min | 796.5 | 634.2 |
| tok/s | 2267.5 | 675.0 |
| p50 s | 1.8544 | 2.0813 |
| p95 s | 3.3896 | 3.7793 |

Con N=48, K=300, R=8 el LLM pide 384 políticas válidas. El 8B tarda 0.48 min; el 32B, 384 / 634.2 = 0.61 min. La simulación sigue en 23.27 min. El total pasa de 23.8 a 23.9 min. N, K y R no cambian: el reloj sigue siendo la simulación. El 8B da más tokens por segundo y no baja de 0.95 de JSON válido, así que sigue como `LLM_MODEL` por defecto. El 32B se evaluará por calidad de política, no por tokens por segundo.

## Validación job 78fea53a

Job `78fea53a-be2d-4bf5-98a3-e9a12b6cba83`, mock, escenario base. Postgres: `started_at` 2026-10-13 17:27:33−06, `finished_at` 18:08:22−06, **2448.5 s (40.8 min)**, 115_500 simulaciones, 385 políticas (1 regla fija + 384 del LLM, 48/48 válidas en las 8 rondas). Semillas de búsqueda: 1–300. El job no corrió holdout (`params` no trae `holdout`; en `metrics` solo hay `seed_set=train`). La mejor política aparece en la ronda 5.

El simulador no se tocó. No apareció un bug de conservación, de semillas ni de mantenimiento apagado, así que no hay test de regresión nuevo.

### Objetivo de entrenamiento y contribución de cada KPI

Fórmula (`sim/objective.py`, pesos en `sim/objective_weights.json`). Mayor es mejor y no está recortado a [0, 1]:

`throughput/400 + on_time_rate/1 − unplanned_h/40 − 0.5·planned_h/20 − 0.5·costo/10000`

Medias sobre las 300 semillas de búsqueda. Los términos reconstruyen el objetivo guardado (0.236458 y 0.957665). El intervalo de la fila es el que ya guardó el job: media ± 1.96·s/√n, no el bootstrap de más abajo.

| | regla fija | mejor (ronda 5) |
|---|---:|---:|
| objetivo | 0.2365 (0.2058, 0.2671) | 0.9577 (0.9440, 0.9714) |
| throughput (órdenes completadas) | 736.16 | 822.49 |
| % a tiempo | 0.4591 | 0.9852 |
| paro no planificado (h) | 20.58 | 12.24 |
| paro planificado (h) | 20.77 | 32.49 |
| costo de mantenimiento | 20_586 | 19_313 |
| órdenes creadas | 839.51 | 839.51 |
| WIP | 103.35 | 17.02 |
| fallas | 46.05 | 27.73 |
| mantenimientos preventivos | 103.86 | 162.50 |

| término | peso | fija | mejor | diferencia |
|---|---:|---:|---:|---:|
| throughput / 400 | 1 | 1.8404 | 2.0562 | +0.2158 |
| % a tiempo | 1 | 0.4591 | 0.9852 | +0.5261 |
| − paro no planificado / 40 | 1 | −0.5145 | −0.3060 | +0.2085 |
| − 0.5 · paro planificado / 20 | 0.5 | −0.5193 | −0.8122 | −0.2929 |
| − 0.5 · costo / 10000 | 0.5 | −1.0293 | −0.9656 | +0.0637 |
| suma | | 0.2365 | 0.9577 | +0.7212 |

El salto lo explica el **% a tiempo** (0.46 → 0.99, +0.53 de los +0.72). Throughput y menos paro no planificado suman unos +0.21 cada uno. El paro planificado empuja al revés: la ganadora hace más preventivo.

La referencia de throughput es 400 y la línea completa unas 740–820 órdenes, así que ese término vale ~2 y sube el nivel de las dos políticas. La regla fija queda en 0.24 porque llega tarde y acumula WIP, no porque el objetivo la recorte.

La ganadora es WEIGHTED (pesos plazo 0.423, setup 0.093, riesgo de desgaste 0.484), `max_pm_per_shift=2`, umbrales M3=0.95, M4=0.92, M5=0.83. M1 y M2 no vienen en el JSON y usan el umbral por defecto 0.75. La regla fija es EDD, umbral 0.75 en las cinco y un preventivo por turno. La ganadora hace más preventivo (162 vs 104) y más paro planificado (32.5 h vs 20.8 h). No gana apagando el mantenimiento.

`orders_created` es igual en las dos (839.51). En cada semilla, creadas = completadas + WIP. La demanda no depende de la política.

### Holdout y estrés

Holdout: semillas 1_000_001–1_000_300, las de `run_search` cuando `holdout_seeds=300`. Intersección con 1–300: vacía. Estrés, las mismas semillas, con `scenario_config`: fallas ×1.3 y demanda ×1.5. IC 95% por bootstrap del objetivo por semilla: 2000 remuestreos, `numpy.random.Generator(PCG64(0))`, percentiles 2.5 y 97.5 de la media. Conservación de órdenes: 0 fallos en las cuatro evaluaciones. `orders_created` coincide entre políticas (holdout 838.83, estrés 1259.12).

| | objetivo | IC 95% | % a tiempo | throughput | paro no planificado (h) |
|---|---:|---:|---:|---:|---:|
| fija, holdout | 0.2483 | (0.2175, 0.2773) | 0.4625 | 737.04 | 20.55 |
| mejor, holdout | 0.9579 | (0.9439, 0.9715) | 0.9868 | 822.20 | 12.31 |
| fija, estrés | −0.3210 | (−0.3392, −0.3029) | 0.1259 | 738.56 | 24.76 |
| mejor, estrés | −0.0693 | (−0.0942, −0.0464) | 0.2744 | 955.87 | 22.10 |

En holdout el hueco se mantiene (+0.71) y otra vez lo lleva el % a tiempo (+0.52). En estrés las dos quedan negativas: la demanda sube a 1259 órdenes y el WIP sigue alto (521 la fija, 303 la ganadora). El hueco baja a +0.25 y ahí el término grande es el throughput (955.9 vs 738.6). La ganadora sigue por delante; el intervalo no se cruza en ninguno de los dos escenarios.

### Workers y los 40 min

`jobs.params` no trae `workers`. `_run_search` deja `workers=None` y `run_search` usa `Settings().SIM_WORKERS`. El `.env` de esta corrida tiene `SIM_WORKERS=16`. Con el default del código (2) y el tiempo interno de una simulación en ráfaga (~0.17 s), 115_500 simulaciones serían unas 2.7 h. El job tardó 40.8 min, que encaja con 16 workers al ritmo sostenido de abajo.

Reloj del job: 2448.5 / 115_500 = **0.0212 s por simulación**. El benchmark del mismo día (100 semillas, un solo pool) fue **0.0121 s**. Repetición el 13 oct por la tarde, regla fija, 300 semillas, 16 workers:

| tanda | reloj | tiempo dentro del proceso | s/sim efectivos |
|---|---:|---:|---:|
| primer pool nuevo | 3.39 s | 0.174 s | 0.0113 |
| pools nuevos 2–6 | ~7.2 s | ~0.37 s | ~0.024 |
| seis tandas en un pool ya abierto | ~7.1 s | ~0.35 s | ~0.024 |

La primera tanda reproduce el benchmark. A partir de la segunda, el tiempo dentro del proceso se duplica (0.17 s → 0.37 s) y el reloj de pared lo sigue. Un pool compartido no acorta la tanda: el arranque de `ProcessPoolExecutor` no es el hueco. Postgres escribe una fila de `metrics` por política al cerrar el job (385 filas, eventos de ronda entre 18:08:21 y 18:08:22), no una escritura por simulación.

16 núcleos a 0.34 s internos dan 300 × 0.34 / 16 = 6.4 s por política. El job hizo 2448.5 / 385 = 6.36 s por política. El paralelo estaba ocupado; el extra frente a los 24 min esperados es la frecuencia sostenida del Core Ultra 7 255H. La ráfaga de 100 semillas cabe en turbo y el job de 40 min no. No hay un cambio pequeño de código que devuelva el 0.0121 s mientras la CPU sigue cargada.

### K para 20 a 30 min

Al ritmo del job (0.0212 s/sim) y con 385 políticas (1 + 48×8, todas válidas, como esta corrida):

| K | simulaciones | minutos |
|---:|---:|---:|
| 150 | 57_750 | 20.4 |
| 180 | 69_300 | 24.5 |
| 200 | 77_000 | 27.2 |
| 300 | 115_500 | 40.8 |

**K por defecto: 180** (perfil `default` en `search/config.py`). N y R siguen en 48 y 8.

Cálculo, con el ritmo sostenido del job (0.0212 s/sim) y 385 políticas (1 regla fija + 48×8, todas válidas):

- Perfil `default`, K=180: 385 × 180 × 0.0212 = 1469 s = **24.5 min**.
- Perfil `final`, K=300: 385 × 300 × 0.0212 = 2448 s = **40.8 min**. Es la corrida larga si sobra tiempo al cierre; N, R y el resto iguales al default.
- Perfil `smoke`: N=2, K=2, R=2, TOP_K=2, holdout 0. Lo usan los tests. No es un presupuesto de búsqueda.

En la laptop hace falta `SIM_WORKERS=16`. `SearchConfig.from_profile("final")` y `from_profile("smoke")` arman esos dos perfiles; `SearchConfig()` es el default.

## Miércoles 14, Optuna

Línea base Optuna (TPE) con el mismo presupuesto que el bucle: `K + N*R*K`. Perfil
`default` (N=48, K=180, R=8) da **69_300 simulaciones** de entrenamiento, en las semillas
`range(1, 181)` y el escenario `base`. El trial 0 es `fixed_rule_policy()`, igual que la
política 0 del bucle. `SIM_WORKERS=16`. Código: `baselines/optuna_search.py`, commit
`d2c7243`; se corrió con `uv run python -m baselines.optuna_search --profile default --seed 1`.

Espacio de búsqueda, con los rangos de los validadores de `policy/schema.py`: umbral
`pm_wear_threshold` por máquina (0.30–0.95), `max_pm_per_shift` (0–3), la regla de despacho
en {EDD, SPT, WEIGHTED, CRITICAL_RATIO} y, cuando la regla es WEIGHTED, los tres pesos
(normalizados a suma 1 por el schema). `rules` va vacía: Optuna no escribe reglas
condicionales. Esa es la ventaja estructural del LLM y conviene tenerla a la vista al leer
la tabla.

| método | simulaciones | mejor objetivo | regla fija | trials | min |
|---|---:|---:|---:|---:|---:|
| Optuna TPE | 69_300 | 1.0061 | 0.2489 | 385 | 13.1 |

Curva del mejor objetivo acumulado, del `history` del JSON:

| simulaciones | 180 | 8_640 | 17_280 | 34_560 | 51_840 | 69_300 |
|---|---:|---:|---:|---:|---:|---:|
| mejor hasta ahí | 0.2489 | 0.9886 | 0.9948 | 0.9995 | 1.0061 | 1.0061 |

Casi todo el valor cae en las primeras 8_640 simulaciones. La política ganadora es
`CRITICAL_RATIO`, `max_pm_per_shift=2`, umbrales entre 0.734 y 0.828 por máquina, sin
reglas. Ningún trial quedó inválido (`failed_trials=0`).

Sobre el reloj: 786 s para 69_300 simulaciones dan **0.0113 s/sim** sostenidos con 16
workers, cerca de los 0.0121 s de la serie corta del lunes y lejos de los 0.0212 s/sim del
job `78fea53a` de 40.8 min, que son la base de la estimación de 24.5 min de más arriba. El
simulador no cambió entre las dos mediciones y no se midió un cambio de código que explique
el factor 1.9; queda anotado como discrepancia abierta. Para comparar métodos la vara sigue
siendo el número de simulaciones, no el minuto.

Lo que esta tabla no dice: no hay holdout (el presupuesto es de entrenamiento y es el mismo
por definición, así que comparar en él favorece a todos por igual). La tabla de los cuatro
métodos con la misma vara es el Prompt 17.

## Miércoles 14, LLM sin retroalimentación

El LLM propone `N*R` políticas con un solo prompt fijo, sin ver objetivos, KPIs ni el top-k
de rondas anteriores. Mismo presupuesto que una búsqueda del perfil y mismos seeds de
entrenamiento: perfil `default` (N=48, K=180, R=8) → **69_300 simulaciones**, semillas
`range(1, 181)`, escenario `base`, `SIM_WORKERS=16`. Las semillas de muestreo son las del
bucle (`rng_seed + lote*10_000`), para que la única variable sea el texto del prompt.
Código: `baselines/llm_nofeedback.py`, commit `726e653`; corrida con
`uv run python -m baselines.llm_nofeedback --profile default --seed 1` contra el mock local.

| método | simulaciones | mejor objetivo | regla fija | válidas | min |
|---|---:|---:|---:|---:|---:|
| LLM sin retroalimentación | 69_300 | 0.9592 | 0.2489 | 384/384 | 15.6 |
| Optuna TPE (de la sección de arriba) | 69_300 | 1.0061 | 0.2489 | — | 13.1 |

Las dos filas son comparables: mismo K, mismas 180 semillas, mismo escenario y el mismo
presupuesto. Con esa vara, Optuna le saca 0.047 al LLM de un solo disparo.

Curva del mejor objetivo acumulado, del `history` del JSON:

| simulaciones | 180 | 8_820 | 17_460 | 34_740 | 43_380 | 69_300 |
|---|---:|---:|---:|---:|---:|---:|
| mejor hasta ahí | 0.2489 | 0.9009 | 0.9009 | 0.9206 | 0.9592 | 0.9592 |

Casi todo el salto está en el primer lote, y del quinto al octavo no se mueve. La política
ganadora es `WEIGHTED` con pesos (0.423, 0.484, 0.093), umbrales M3=0.95, M4=0.92, M5=0.83,
`max_pm_per_shift=2` y una regla (`queue_len_gt=4 → BATCH_SAME_PRODUCT`). Ninguna propuesta
salió inválida.

**Lo que este número no mide, y hay que decirlo al lado.** Contra el mock, esta línea base
no puede separarse del bucle. El mock deriva cada política de la `seed` y nunca lee el
contenido del prompt (`llm/mock_server.py`: `_seed_from` mira `body["seed"]` y
`generate_policy(seed)` no toca los mensajes), así que con las mismas semillas de muestreo
los 384 candidatos son el mismo conjunto que vería el bucle y el mejor objetivo sale igual
por construcción. El 0.9592 es el techo de 384 sorteos del mock, no una medida de lo que
aporta la retroalimentación. Esa comparación necesita vLLM, que sí lee el prompt, y se
repite en la sesión GPU 2. El Prompt 17 confirma la igualdad con la búsqueda del bucle
corrida al mismo perfil.

Sobre el reloj: 15.6 min con 16 workers (0.0135 s/sim), entre los 0.0113 s/sim de la corrida
de Optuna y los 0.0212 s/sim del job `78fea53a`.

## Miércoles 14, curva de eficiencia

Métrica de la sección 7 del plan: el mejor objetivo encontrado contra simulaciones gastadas,
una curva por método, todos con el mismo presupuesto de entrenamiento (perfil `default`,
K=180, semillas `range(1, 181)`, escenario `base`). El umbral se fijó **antes** de mirar los
resultados, sobre la mejora y no sobre el objetivo (que no está acotado a 0–1):

`target = fixed + 0.9 * (best_global - fixed) = 0.2489 + 0.9*(1.0061 - 0.2489) = 0.9303`

Código: `eval/efficiency.py`, commit `efd808a`. La búsqueda del bucle de este perfil y semilla
se corrió nueva (`search.loop --seed 1 --holdout 0`); el job `78fea53a` es K=300 y no era
comparable. Se usó `--holdout 0` porque esas semillas se suman a `simulations_total` y
romperían el presupuesto igual.

| método | mejor train | holdout | IC 95% | % a tiempo holdout | sims gastadas | sims al 90% | notas |
|---|---:|---:|---|---:|---:|---:|---|
| regla fija | 0.2489 | 0.2483 | [0.2175, 0.2773] | 46.2% | 180 | no alcanza | definitivo |
| Optuna TPE | 1.0061 | 0.9906 | [0.9779, 1.0031] | 99.6% | 69_300 | 3_060 | definitivo |
| LLM sin retroalimentación | 0.9592 | 0.9579 | [0.9439, 0.9715] | 98.7% | 69_300 | 43_380 | mock, no es medida del LLM |
| bucle con retroalimentación | 0.9592 | 0.9579 | [0.9439, 0.9715] | 98.7% | 69_300 | 43_380 | mock, no es medida del LLM |

Holdout: las 300 semillas desde 1_000_001, las de `run_search`, con IC 95% por bootstrap de
2000 remuestreos y `PCG64(0)`. Son 4 × 300 = 1_200 simulaciones **fuera** del presupuesto de
búsqueda. El % a tiempo se recalcula desde el `best_policy` guardado de cada método.

Cruce con la validación del martes, que no se tocó: la regla fija da 46.2% a tiempo con IC
[0.2175, 0.2773] y la política del bucle 98.7% con [0.9439, 0.9715], frente a los (0.218,
0.277) y (0.944, 0.972) que ya estaban en `BENCHMARKS.md`. El pipeline de holdout y bootstrap
reproduce esos números, así que la comparación de arriba se apoya en el mismo instrumento.

**Qué se puede concluir hoy y qué no.** La comparación definitiva de esta tabla es la regla
fija contra Optuna, porque ninguna de las dos pasa por el LLM. Optuna gana en las 180 semillas
de entrenamiento (1.0061 contra 0.2489) y en holdout (0.9906 contra 0.2483), y llega al umbral
en **3_060** simulaciones contra las 43_380 del LLM de un solo disparo y del bucle.

Las dos filas del LLM son **el mismo número por construcción**, no por casualidad: las curvas
son idénticas punto por punto (9 puntos, los mismos valores). El mock deriva cada política de
la semilla y no lee el prompt, y las dos corridas usan las mismas semillas de muestreo, así
que los 384 candidatos son el mismo conjunto y el orden por lotes es el mismo que por rondas.
Lo que esa igualdad mide es el techo de 384 sorteos del mock, no lo que aporta la
retroalimentación. Como el mock es un generador aleatorio sobre el espacio de políticas, la
comparación que sí queda medida es **TPE contra búsqueda aleatoria**: 1.0061 contra 0.9592 y
3_060 contra 43_380 simulaciones es la eficiencia de muestreo de TPE, y el resultado es que le
saca 0.047 con catorce veces menos simulaciones.

La ventaja estructural del LLM —hasta 5 reglas condicionales, que Optuna no escribe nunca—
no se puede evaluar con el mock. La política ganadora del mock usa una regla
(`queue_len_gt=4 → BATCH_SAME_PRODUCT`) y aun así pierde, pero eso no dice nada sobre reglas
escritas por un LLM: dice que 384 sorteos no le ganan a TPE. Si el LLM llega a un resultado
comparable cuando corra contra vLLM, el mensaje es que llega con esas simulaciones y que puede
explicar el porqué con reglas legibles; hoy esa frase todavía no está medida. La repetición
contra vLLM es la misma orden, sin tocar código, con `--llm-source vllm` sobre los JSON de esa
sesión.

Granularidad de cada curva: es la granularidad con la que el método puede actuar sobre la
información. Por trial en Optuna (cada trial ve los anteriores, 385 puntos), por ronda o lote
en el bucle y en el LLM sin retroalimentación (las N candidatas se proponen juntas y después
se simulan, 9 puntos; un punto por candidata inflaría al bucle), y un solo punto en la regla
fija, que se extiende horizontal hasta el presupuesto. Con esa granularidad, la columna "sims
al 90%" del one-shot y del bucle está cuantizada a lotes de 8_640 simulaciones, así que su
cruce cae en la frontera del lote y no antes.

JSON con las cuatro curvas: `bench/results/efficiency_20261014.json` (local; `bench/results`
está ignorado). La figura queda para el jueves en Chart.js, como permite el plan: no se sumó
matplotlib.
