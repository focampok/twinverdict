# Pendientes del miércoles 14

Hecho el martes: búsqueda mock de punta a punta en Postgres (job `78fea53a`,
40.8 min, 115_500 simulaciones), perfiles en `search/config.py`, y cada job de
búsqueda guarda N, K, R, workers, modelo, perfil, semillas, commit y s/sim.
La instancia GPU del martes está destruida. Mañana no se crea otra salvo la
lista escrita de la sesión 2, al final del día.

Presupuesto de las comparaciones: el mismo número de simulaciones que el perfil
`default` (N=48, K=180, R=8: 1 regla fija + 384 propuestas = 69_300 simulaciones
de entrenamiento). Si una corrida usa el perfil `final` (K=300), las líneas base
de esa corrida usan ese mismo K. El número lo da el simulador.

## En orden

1. **Líneas base con el mismo presupuesto.** Regla fija (ya es la política 0 de
   la búsqueda), Optuna (TPE) sobre los parámetros numéricos y la regla de
   despacho como variable categórica, y un LLM sin retroalimentación (propone
   una vez, sin el prompt de las rondas anteriores). Las tres y el bucle con
   feedback gastan las mismas simulaciones. Si Optuna empata o gana, se dice.
2. **Curva objetivo vs simulaciones.** Mejor objetivo acumulado contra
   simulaciones gastadas, para el bucle y para cada línea base. Sale de lo ya
   guardado en `search_runs` y `runs` (prompts, candidatas, objetivos por ronda).
3. **Replay.** La búsqueda ya persiste esa curva. Falta que `MODE=replay`
   reproduzca una corrida grabada con la GPU apagada, rotulada como replay, para
   la URL de la demo.
4. **Calibración.** Ajustar desgaste→riesgo con AI4I 2020 o C-MAPSS
   (`sim/calibration.py`). Declarar qué se calibró y qué sigue siendo planta
   simulada. No afirmar un despliegue en fábrica.
5. **Sesión GPU 2, solo con lista escrita y si queda tiempo.** Primero
   `infra/gpu/gpu.sh bench-sim` (18 workers en los 20 vCPU; no se corrió el
   martes). Después una búsqueda con el modelo ya elegido. Comparar
   `Qwen/Qwen3-8B` y `Qwen/Qwen3-32B` por **calidad de política** (objetivo en
   las semillas de holdout, misma N/K/R), no por tokens/s. El 8B sigue como
   default hasta que esa comparación diga otra cosa. Al terminar: `stop` y
   destruir la instancia. Worker nativo, `SIM_WORKERS=18`, Postgres de Railway
   con `sslmode=require` o Postgres local y sync después. Pasos en
   `docs/SESION_GPU.md`.

## Tarjeta de operador

El número que el operador tiene que ver es el **% a tiempo**, no el objetivo
compuesto. En las 300 semillas de búsqueda la regla fija entrega a tiempo el
46% y la política de la ronda 5 el 99% (0.459 → 0.985). En holdout, semillas
que la búsqueda no vio, queda 46% → 99% (0.463 → 0.987), IC 95% del objetivo
(0.218, 0.277) contra (0.944, 0.972). La ganadora hace más mantenimiento
preventivo (162 contra 104), no menos, y las dos ven las mismas órdenes creadas.

En estrés (+30% fallas, demanda ×1.5) las dos empeoran y el hueco lo lleva el
throughput, no el % a tiempo. La tarjeta no promete el mismo salto bajo ese
pico. El objetivo compuesto no está acotado a 0–1: la referencia de throughput
es 400 y la línea completa unas 800. Aprobación humana antes de recomendar.
Detalle en `docs/BENCHMARKS.md`, sección "Validación job 78fea53a".
