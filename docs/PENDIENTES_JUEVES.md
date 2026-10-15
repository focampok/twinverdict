# Pendientes del jueves 15

Hecho el miércoles: líneas base (regla fija, Optuna TPE, LLM sin retroalimentación), curva de
eficiencia, calibración AI4I, corte de planta (`failure_midpoint` 0.95 / `failure_steepness`
18), sesiones GPU 2 y GPU 4. La **corrida oficial del bucle con planta calibrada** es el job
`285d1787-5d7c-464a-9897-4c585663f088` (tabla en `docs/BENCHMARKS.md`, sección GPU 4). Fuente
de la demo: `bench/results/operator_card_285d1787-5d7c-464a-9897-4c585663f088.json` y su
replay. % a tiempo holdout: **50.6% → 98.8%**.

**Mañana es solo UI/UX.** Sin GPU. Sin re-correr búsquedas ni baselines.

## En orden

1. **Texto de la tarjeta de operador con `guard/numbers.py`.** Fuente:
   `operator_card_285d1787-…json`. El mapa plano `numbers` ya está; el texto que ve el
   operador se verifica contra ese mapa y ninguna cifra se escribe a mano. El número que
   importa es el **% a tiempo** (50.6% → 98.8%), no el objetivo compuesto.

2. **UI de solo lectura.** `load_replay` / el snapshot de `285d1787` alimentan la pantalla.
   La UI no llama al LLM ni al simulador. Prioridad: tarjeta de operador y curva de
   eficiencia (Chart.js sobre `bench/results/efficiency_20261015.json`). Si el tiempo no da,
   el resto de la UI se recorta.

3. **`MODE=replay` para la URL de la demo**, rotulado como replay, con la GPU apagada.

4. **Pendiente corto, sin GPU: ronda 2 del job 285d1787 (34 inválidas).** Casi todas son
   `rules.*.if` con condición vacía (`machine` y `product_waiting` nulos). Revisar prompt /
   schema / postproceso. No bloquea la UI; los números oficiales ya están en BENCHMARKS.

5. **Cierre.** `docs/PENDIENTES_VIERNES.md` si queda algo.

## Lo que hay que decir en cualquier presentación

- Los números del bucle oficial son **vLLM real** (Qwen3-8B), planta calibrada, job
  `285d1787`. No son el mock.
- Optuna sigue por delante en objetivo compuesto (1.52 vs 1.38); el bucle gana al one-shot
  (1.38 vs 1.23) y entrega el salto de % a tiempo de la tarjeta.
- El objetivo compuesto no está acotado a 0–1 y no se compara entre configuraciones de planta
  distintas.
- La calibración es de **forma**, con un dataset público sintético; no es un gemelo de una
  fábrica concreta ni promete un despliegue real.
- En holdout la regla fija entrega a tiempo el 50.6% y la mejor política el 98.8%; en estrés
  el hueco lo lleva el throughput, no el % a tiempo.
