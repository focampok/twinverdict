# Pendientes del jueves 15

Hecho el miércoles: las tres líneas base con el mismo presupuesto (regla fija, Optuna TPE y
LLM sin retroalimentación) y la tabla de eficiencia de los cuatro métodos en
`docs/BENCHMARKS.md`; calibración real de la curva desgaste → riesgo con AI4I 2020
(`docs/CALIBRATION.md`); replay y corrida congelada con snapshot de la tarjeta de operador
(`docs/REPLAY.md`). Sigue **sin haber nada de UI**: la tarjeta es un JSON.

## En orden

1. **Corte de calibración, antes de las corridas finales.** `PlantConfig` adopta
   `calibrated_plant_config()` como configuración por defecto: `failure_midpoint` 0.72 → 0.95
   y `failure_steepness` 14 → 18, la forma ajustada con AI4I 2020. Es un **cambio anunciado en
   un corte limpio**, no un ajuste silencioso, y hay que decir en voz alta que **los objetivos
   anteriores y posteriores al corte no son comparables**. Después del cambio se **re-corren
   los cuatro métodos** (regla fija, Optuna, LLM sin retroalimentación y bucle) con esa
   configuración y el mismo presupuesto, y la tabla de eficiencia se rehace con esos números:
   la actual quedó corrida entera con la config vieja y no se mezcla.

   El nivel por minuto no entra en el corte: sigue siendo un supuesto de planta, porque AI4I no
   trae duración por registro (`level_calibrated: false` en `sim/calibrated_params.json`).

   Lo que el corte **no** debería mover es el titular de la tarjeta: con y sin calibrar, el % a
   tiempo va de 44.7% a 48.6% en la regla fija y de 98.4% a 99.2% en la mejor política. Si al
   re-correr sale otra cosa, decirlo.

2. **Figura de la curva de eficiencia en Chart.js** (Prompts 17 y 18). Hoy quedó solo el JSON
   con las cuatro curvas, `bench/results/efficiency_20261014.json`, porque no se sumó
   matplotlib. La tabla de los cuatro métodos ya está en `BENCHMARKS.md`.

3. **Texto de la tarjeta de operador con `guard/numbers.py`.** La tarjeta
   (`operator_card_<job_id>.json`) tiene las métricas y el mapa plano `numbers`; falta que el
   texto que ve el operador se verifique contra ese mapa y que ninguna cifra se escriba a mano.
   El número que el operador tiene que ver es el **% a tiempo**, no el objetivo compuesto.

4. **UI de solo lectura.** `load_replay(job_id)` devuelve todo lo que hace falta; la UI no debe
   llamar al LLM ni al simulador. La tarjeta de operador y la curva de eficiencia son la
   prioridad; si el tiempo no da, el resto de la UI se recorta.

5. **`MODE=replay` para la URL de la demo**, rotulado como replay, con la GPU apagada.

6. **Sesión GPU 2, si no se hizo el miércoles.** `Qwen/Qwen3-8B` contra `Qwen/Qwen3-32B` por
   calidad de política (no por tokens/s), y una búsqueda con el LLM sin retroalimentación
   contra vLLM real: es la comparación que el mock no puede dar, porque el mock no lee el
   prompt. Al terminar: `stop` y destruir la instancia. Todo por `infra/gpu/gpu.sh`.

7. **Cierre.** `docs/PENDIENTES_VIERNES.md` si queda algo, y la decisión de qué config de
   planta acompaña los números finales.

## Lo que hay que decir en cualquier presentación

- El LLM es el **mock**. Los números del bucle y del LLM sin retroalimentación no miden al
  modelo; contra el mock son el mismo conjunto de candidatos por construcción. Lo definitivo
  de hoy es la regla fija contra Optuna.
- El objetivo compuesto no está acotado a 0–1 y no se compara entre configuraciones de planta
  distintas.
- La calibración es de **forma**, con un dataset público sintético; no es un gemelo de una
  fábrica concreta ni promete un despliegue real.
- La regla fija entrega a tiempo el 46% y la mejor política el 99% en semillas que la búsqueda
  no vio; en estrés el hueco lo lleva el throughput, no el % a tiempo.
