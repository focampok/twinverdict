# Calibración de la curva desgaste → riesgo

Qué se calibró, con qué datos, y qué sigue siendo supuesto de planta simulada. El detalle
numérico está en `sim/calibrated_params.json`; el código, en `sim/calibration.py`.

## Dataset

- **AI4I 2020 Predictive Maintenance** (S. Matzka, 2020), UCI Machine Learning Repository,
  dataset 601. Licencia CC BY 4.0.
- URL: <https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset>
- Descarga: `uv run python -m bench.download_ai4i` → `data/raw/ai4i2020.csv` (10 000 filas).
  `data/raw/` está en `.gitignore`: el CSV no se versiona.
- Descargado el **2026-10-14**. sha256 del CSV:
  `dc6630cd9b1f0f853922fad78a1b6436570d3f1ec863f1dd5c4340ac56bc8a8e`.
- Ajuste: `uv run python -m sim.calibration data/raw/ai4i2020.csv`.
- El fixture de los tests (`tests/fixtures/ai4i_sample.csv`, 200 filas sintéticas con las
  mismas columnas) se genera con una logística conocida y **no** es el dataset real: el CI
  no descarga nada.

## Qué se usa como "falla por desgaste"

AI4I trae cinco modos. Medidos por tramos de desgaste (tasa por registro):

| desgaste (min) | n | TWF | OSF | HDF | PWF | RNF |
|---|---:|---:|---:|---:|---:|---:|
| 0–50 | 2349 | 0.0000 | 0.0000 | 0.0111 | 0.0102 | 0.0017 |
| 50–100 | 2271 | 0.0000 | 0.0000 | 0.0123 | 0.0101 | 0.0013 |
| 100–150 | 2290 | 0.0000 | 0.0000 | 0.0118 | 0.0105 | 0.0013 |
| 150–200 | 2289 | 0.0004 | 0.0122 | 0.0100 | 0.0070 | 0.0031 |
| 200–250 | 799 | 0.0551 | 0.0851 | 0.0138 | 0.0100 | 0.0025 |

**TWF y OSF** son los dos modos que solo aparecen a desgaste alto: cero hasta los 150 min y
disparo después. **HDF, PWF y RNF** tienen tasa plana en todo el rango, así que no dependen
de la herramienta (son temperatura, potencia y azar). La etiqueta del ajuste es, entonces,
TWF ∪ OSF: 141 registros de 10 000. El enunciado del prompt ofrecía "falla total o TWF +
RNF"; los datos dicen que el par que depende del desgaste es TWF + OSF, y RNF es fondo plano.
La elección está en `WEAR_DRIVEN_MODES` y hay un test que la fija.

El término `base` de la logística absorbe el fondo: HDF, PWF y RNF aparecen en 226 registros
y su tasa no cambia con el desgaste.

## El ajuste

Desgaste normalizado a [0, 1] dividiendo entre el máximo observado (253 min), que es la misma
escala que usa el simulador. Máxima verosimilitud sobre

`P(falla | desgaste) = base + (1 - base) · sigmoide(steepness · (desgaste - midpoint))`

por rejilla (una pasada gruesa y otra fina alrededor). No hay scipy en el proyecto y tres
parámetros no justifican añadirlo; la rejilla es lenta pero determinista y auditable.

| parámetro | antes (simulador) | después (AI4I) |
|---|---:|---:|
| `midpoint` | 0.72 | **0.9500** |
| `steepness` | 14.0 | **18.0** |
| `base` por registro | — | 0.0000 |
| log-verosimilitud | — | −457.06 |

El ajuste describe los datos:

| desgaste | n | observado | predicho |
|---|---:|---:|---:|
| 0.00–0.50 | 5861 | 0.0000 | 0.0000 |
| 0.60–0.70 | 1191 | 0.0025 | 0.0045 |
| 0.70–0.80 | 1137 | 0.0299 | 0.0266 |
| 0.80–0.90 | 613 | 0.1370 | 0.1419 |
| 0.90–0.95 | 48 | 0.3333 | 0.3894 |
| 0.95–1.00 | 11 | 0.3636 | 0.6106 |

El último tramo sobreestima y hay que decirlo: son 11 filas, dos de ellas con desgaste 250–275
min que fallan las dos. Sin la cota de `steepness` el máximo verosímil se iba a una escalera
perfecta sobre esas dos filas, que no describe nada.

## Qué NO se calibró

- **El nivel por minuto (`base_per_min`)**: AI4I no trae duración por registro. Una
  probabilidad por registro no se convierte en una tasa por minuto sin inventar cuánto dura
  cada registro, y el dataset no lo dice. Así que `base_per_min` conserva los valores del
  simulador (0.0015, 0.0012, 0.0018) y **queda como supuesto declarado**, no como resultado
  del ajuste. `sim/calibrated_params.json` lo marca con `level_calibrated: false`.
- El detalle está anotado en el propio JSON, en `level_note`.

**Sigue siendo supuesto de planta simulada**, sin cambio: demanda y llegada de órdenes,
tiempos de proceso y de setup, las 5 máquinas, mezcla de productos, tiempos y costos de
reparación, costo y duración del mantenimiento preventivo, reglas de despacho y la política.

**No se afirma**: que esto sea una planta real, ni el ROI de un cliente, ni nada sobre datos
propietarios. La curva de riesgo se apoya en un dataset público *sintético* de una línea de
producción genérica; es una calibración de forma, no un gemelo de una fábrica concreta.

## Impacto

Misma política, dos configuraciones de planta; lo único distinto entre columnas es
`failure_midpoint` y `failure_steepness`. 100 semillas de holdout (1 000 001–1 000 100, las
que no vio ninguna búsqueda), escenario `base`, 16 workers.
Comando: `uv run python -m bench.calibration_impact`.

| política | config | objetivo | % a tiempo | fallas | paro no plan. (h) |
|---|---|---:|---:|---:|---:|
| regla fija | por defecto | 0.2275 | 44.7% | 45.74 | 20.3614 |
| regla fija | calibrado | 0.7424 | 48.6% | 27.30 | 12.4468 |
| mejor del bucle | por defecto | 0.9480 | 98.4% | 27.56 | 12.3640 |
| mejor del bucle | calibrado | 1.4047 | 99.2% | 4.58 | 1.9679 |

Lectura:

- **El titular de la tarjeta de operador aguanta.** El % a tiempo apenas se mueve: 44.7% →
  48.6% en la regla fija y 98.4% → 99.2% en la mejor política. La historia "46% → 99%"
  no depende de la calibración. Los dos valores con la config por defecto reproducen los de
  la validación del martes (44.7% contra 46.3% y 98.4% contra 98.7%), que es lo que se
  esperaba: son 100 semillas de las 300.
- **El objetivo compuesto sí se mueve mucho** (0.948 → 1.4047), y no hay que leerlo como una
  mejora del método: el objetivo no está acotado a 0–1 y el término de throughput pesa, así
  que menos fallas → más producción → objetivo más alto. Con la calibración la planta es más
  benigna (los fallos se concentran a desgaste muy alto), y eso se ve en `fallas` y en el
  paro no planificado, que caen a un tercio.
- **Conclusión:** los objetivos de dos configuraciones distintas **no son comparables entre
  sí**; solo lo son dentro de la misma configuración. Para comparar métodos, lo que vale es
  la tabla de eficiencia de `docs/BENCHMARKS.md`, corrida toda con la config por defecto.

La "mejor política del martes" no se pudo re-pull: el job `78fea53a` no está en el Postgres
local (`search_runs` solo tiene dos filas del perfil `smoke`, de los tests). Se usó la mejor
política del bucle de hoy con el perfil `default`, cuyos números de holdout reproducen los
del martes, así que muy probablemente es la misma. La comparación es entre columnas con la
misma política, así que lo que se mide es el efecto de calibrar, no el valor absoluto.

## ¿Se usa como parámetro por defecto de aquí en adelante?

**Recomendación: no cambiar el default todavía.** El cambio es científicamente razonable,
pero `PlantConfig` por defecto es la vara con la que se midió todo lo anterior (lunes,
martes, los cuatro métodos de hoy). Cambiarlo ahora rompería la comparabilidad de los
objetivos ya publicados y de la tabla de eficiencia.

La forma calibrada está disponible sin tocar el default, en una línea:

```python
from sim.calibration import calibrated_plant_config

metrics = simulate(policy, seed, calibrated_plant_config())
```

Si se decide adoptarla, conviene hacerlo como un cambio anunciado y en un corte limpio
(después de las corridas finales del jueves), dejando dicho que los objetivos de antes y
después de ese punto no se comparan. Decisión pendiente.
