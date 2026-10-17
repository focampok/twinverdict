# 2D-ANIMATION — TwinVerdict

Guía de la pieza visual de TwinVerdict para el AMD Developer Hackathon ACT III. **Cierre duro: dom 18 oct 2026, 09:00 GT**; meta interna: enviar el sábado en la noche. Prosa en español; **lo que se ve en pantalla y la voz en off van en inglés.** Preparada el 12 oct 2026 a partir de tus respuestas y de una lectura del repo (sin cambios de código).

> **Decisión (12 oct):** TwinVerdict **sí lleva su pieza 2D**, pero la fase de UX/UI (que incluye esta pieza y la paleta definitiva) es la **ÚLTIMA fase** del proyecto: después del bucle de búsqueda, las líneas base, la tarjeta del operador y la evaluación. Antes de esa fase no se toca nada visual.

---

## 1. Objetivo y qué se lleva el jurado

**Una sola idea, vista y no leída:** *con la política propuesta la línea pasa menos tiempo en rojo y por eso entrega más órdenes a tiempo.*

Frase del video (los números se fijan **después** de la búsqueda del miércoles, con los KPIs de la política ganadora en `sim/kpis.py`):
> "Red time drops from **X** to **Y** minutes — that's **Z** more orders on time."

**El costo no va de titular.** Puede moverse al lado equivocado (más PM planificado y más `maintenance_cost`, ambos con peso 0.5 en `sim/objective_weights.json`) y no se ve en el dibujo. Se queda en la tarjeta del operador.

## 2. Entregable elegido (máx. 2 h de trabajo visual)

**Una franja Gantt lado a lado con playhead**, estilo flat flow-diagram: dos carriles (Baseline y Proposed) de 5 filas finas cada uno (una por máquina, 28–36 px), **un solo eje de tiempo compartido** y **un solo botón de play** que mueve los dos playheads. Misma semilla en los dos carriles. Datos grabados (REPLAY), no un feed en vivo. Selector de 2–3 semillas para mostrar que no es una corrida afortunada.

Por qué Gantt y no "5 cajas con colas": el Gantt es más barato y más honesto para leer la diferencia entre políticas. La vista de flujo (5 cajas en fila con sus colas en el instante t) **sale gratis** del Gantt en la posición del playhead y queda como extra opcional (§9).

### ⚠ Requisito previo (NO cabe en las 2 h visuales)

Hoy **no existe una línea de tiempo por máquina**:
- `run_simulation` (`sim/model.py:264`) devuelve solo totales (`SimResult`).
- Los eventos de `_machine_loop` (PM `:179`, setup `:193`, falla `:237`, reparación `:242`, fin de orden `:258`) se pierden en contadores.
- `RunEvent` (`db/models.py:90`) solo recibe 3 filas por job desde `worker/main.py`.

Hay que agregar en el simulador (trabajo del sim, no de la pieza visual):
- Un parámetro `record: list | None = None` que por defecto no hace nada, para mantener la pureza y el pickling de `simulate()` en `ProcessPoolExecutor` (`sim/runner.py:46-64`).
- Un **punto de entrada aparte** que corra **una semilla y dos políticas** y devuelva `(kpis, intervalos)`. **Nunca** dentro del bucle de búsqueda.
- Intervalos, no eventos sueltos: `(machine, start, end, kind)` con `kind ∈ {processing, setup, pm, down, idle}`.
- Volumen: horizonte de 10,080 min (`sim/config.py`), ~840 órdenes, 5 máquinas → < 1,000 filas por política, decenas de KB. Se publica como **JSON estático**.

Estimado: 1–2 h extra. Va en la agenda del sim (miércoles o jueves), **antes** de empezar estas 2 h.

## 3. Pasos con tiempo fijo (total 120 min, con el JSON ya generado)

| Min | Paso | Salida |
|---|---|---|
| 0–10 | Tokens de paleta y esqueleto `index.html` + `gantt.js` | Página vacía |
| 10–45 | Render SVG de un carril: 5 filas, rectángulos por intervalo coloreados por `kind`, eje de tiempo en horas de planta | Un carril estático |
| 45–65 | Segundo carril (Proposed) con el mismo eje; etiquetas "Baseline: fixed rule (threshold 0.75, 1 PM/shift, EDD)" y "Proposed policy" | Lado a lado |
| 65–85 | Playhead compartido + play/pause + **saltos a la ventana interesante** (el racimo de fallas donde los carriles divergen) con marcadores | Animación |
| 85–100 | Contadores bajo cada carril hasta el playhead: minutos en rojo (`down`) y órdenes a tiempo; selector de semilla (2–3) | Evidencia visible |
| 100–110 | Página de Netlify (§7), botón "See it live" a Railway en replay, badge **REPLAY** | Página completa |
| 110–120 | `prefers-reduced-motion`, grabación de 10–12 s y del plano de "dolor" (solo Baseline) | Checklist (§10) |

## 4. Storyboard y voz en off (inglés)

Encaja en el guion de 3:00 del PLAN (`docs/PLAN.md:226`) **entre 0:40 y 0:55**, en la transición entre la tarjeta del operador y "regla fija como base", con **10–12 s**. **No reproduzcas los 7 días completos:** salta a la ventana del racimo de fallas.

| Tiempo (en el video) | En pantalla | Voice-over (EN) |
|---|---|---|
| 0:40–0:42 | Los dos carriles en la misma semilla, playhead quieto en el inicio de la ventana | "Same demand, same seed. The only thing that changes is the policy." |
| 0:42–0:45 | El playhead avanza; los carriles se parecen | "Here's a week of the line, zoomed into the hardest stretch." |
| 0:45–0:51 | **Divergencia:** Baseline se llena de rojo (fallas y reparaciones); Proposed muestra ámbar (PM planificado) y menos rojo | "The fixed rule waits for machines to break. The proposed policy services them first." |
| 0:51–0:55 | Contadores: rojo X → Y min, +Z órdenes a tiempo | "Less red, more orders out the door on time — measured by the simulator, not the model." |

**Plano opcional de dolor (0:20, ~5 s):** solo el carril Baseline, ámbar y rojo con órdenes tarde apilándose. VO: *"Unplanned stops pile up — and late orders follow."*

## 5. Fuentes de datos (reales)

| Fuente | Qué aporta |
|---|---|
| **Nuevo:** `intervals_<seed>.json` del punto de entrada de §2 | `{seed, policies: {baseline: {kpis, intervals:[{m, start, end, kind}]}, proposed: {...}}}` |
| `policy/schema.py:146` | Definición de la base (umbral 0.75 plano, 1 PM por turno, EDD, sin reglas) para la etiqueta |
| `sim/kpis.py` | `unplanned` y órdenes a tiempo para los contadores y el titular |
| `sim/config.py` | `horizon_min = 10080`, `shift_min = 480` para el eje |
| Modo `MODE=replay` (`docs/PLAN.md:161`) | La URL de Railway sigue viva con la GPU apagada |

En el cliente: un `fetch` del JSON y el playhead se calcula ahí. **No pidas filas de `RunEvent` a Postgres por cuadro.**

## 6. Paleta

**Provisional, se reemplaza en la fase de UX/UI (la última).** Hoy `ui/templates/index.html` tiene 12 líneas y no define colores. Estos tokens (flat, de alto contraste) sirven para prototipar; cuando esa fase fije la paleta de la app, la franja Gantt adopta esos mismos tokens. Solo se conserva la semántica: rojo = paro no planificado, ámbar = PM.

| Token (provisional) | Valor | Uso |
|---|---|---|
| `--bg` | `#0f1115` | Fondo |
| `--panel` | `#181b22` | Fondo de carriles |
| `--text` | `#e8ebf0` | Texto |
| `--muted` | `#8a93a3` | Ejes y etiquetas |
| `--processing` | `#3b82f6` | Procesando |
| `--setup` | `#a78bfa` | Setup |
| `--pm` | `#f59e0b` | Mantenimiento planificado (ámbar) |
| `--down` | `#ef4444` | Paro no planificado (rojo) |
| `--idle` | `#2a2f3a` | Ociosa |
| `--playhead` | `#ffffff` | Playhead |

## 7. Página estática en Netlify (estilo pitch deck)

```
netlify-visual/
  index.html        # secciones de abajo
  gantt.js          # render SVG + playhead
  data/intervals_<seed>.json   # 2–3 semillas, generadas por el punto de entrada de §2
```

Secciones:
1. **Hero:** "TwinVerdict — an LLM proposes, the simulator decides". Botón **See it live →** (URL de Railway en `MODE=replay`).
2. **The operator card:** captura de la tarjeta (recomendación + números verificados + aprobar/rechazar).
3. **The evidence:** la franja Gantt lado a lado, el selector de semilla y el badge **REPLAY**.
4. **How it works:** LLM en AMD MI300X (vLLM) → políticas en JSON validado → simulador sobre N semillas → IC 95 %.
5. **Footer:** repo (MIT), "simulated plant, not a real factory", **See it live →**.

Respaldo: si Railway cae, la página sigue mostrando la franja (datos estáticos) y avisa en el botón.

## 8. Herramientas

```bash
# Sin dependencias: SVG + JS puro.
cd netlify-visual && python3 -m http.server 8080
npm i -g netlify-cli && netlify deploy --dir netlify-visual --prod
# Generar el JSON (cuando exista el punto de entrada de §2), por ejemplo:
#   uv run python -m sim.record --seeds 11 23 37 --out netlify-visual/data/
# (el nombre del módulo es una propuesta; no existe todavía)
```

## 9. Lista de recortes (en este orden)

1. Vista de flujo (5 cajas + colas en el instante t).
2. Selector de semilla: una sola semilla.
3. Plano de "dolor" a 0:20.
4. **Último recurso:** interruptor Baseline/Proposed en vez de lado a lado. Ojo: así **ya no prueba nada, solo ilustra.**
5. **Nunca recortar:** misma semilla, eje compartido, rojo = paro no planificado, badge REPLAY, números del simulador.

## 10. Checklist de aceptación

- [ ] Los dos carriles usan la misma semilla y el mismo eje; un solo play mueve ambos.
- [ ] Los colores siguen `kind`; el rojo es solo `down`.
- [ ] Los contadores coinciden con `sim/kpis.py` para esa semilla y política (sin números a mano).
- [ ] Badge REPLAY visible; ningún dato viene de la GPU en vivo.
- [ ] Salto directo a la ventana de divergencia (sin reproducir 7 días).
- [ ] `prefers-reduced-motion` desactiva la animación del playhead (queda estático con marcadores).
- [ ] "See it live" abre Railway en replay; si falla, la página sigue sirviendo la evidencia.
- [ ] Clip de 10–12 s grabado en 1080p para 0:40–0:55.
- [ ] La grabación del simulador no se ejecuta dentro del bucle de búsqueda; `simulate()` sigue siendo pura.

## 11. Prompt para Claude Code

```text
Read 2D-ANIMATION.md (spec). Two separate tasks; do task A only if intervals JSON does not exist yet.

TASK A (simulator, ~1-2 h, separate from the visual budget):
- Add an optional `record: list | None = None` parameter threaded into sim/model.py so that _machine_loop
  appends intervals (machine, start, end, kind) with kind in {processing, setup, pm, down, idle}.
  Default None must be a no-op; keep simulate() pure and picklable (sim/runner.py uses ProcessPoolExecutor).
- Add a separate entry point (e.g. sim/record.py) that runs ONE seed for TWO policies (baseline from
  policy/schema.py and a given proposed policy JSON) and writes
  {seed, policies:{baseline:{kpis, intervals}, proposed:{kpis, intervals}}} to JSON. Never call it from the search loop.
- Add tests: recording does not change KPIs; intervals per machine do not overlap and cover the horizon.

TASK B (visual, timebox 2 h):
- Create files only under ./netlify-visual/ (index.html, gantt.js, data/). Do not modify other files. Do not commit.
- No build, no frameworks. Plain HTML + SVG + vanilla JS. All on-screen text in English.
- Two lanes (Baseline, Proposed), 5 thin rows each (28-36 px), one shared time axis (plant hours),
  one play button moving both playheads, markers to jump to the failure cluster where lanes diverge.
- Counters under each lane up to the playhead: unplanned (red) minutes and on-time orders, computed from
  the intervals/kpis in the JSON, never typed by hand. Seed selector for 2-3 JSON files. "REPLAY" badge.
- Palette tokens (PROVISIONAL, to be replaced by the app palette defined in the final UX/UI phase): --bg #0f1115 --panel #181b22 --text #e8ebf0 --muted #8a93a3
  --processing #3b82f6 --setup #a78bfa --pm #f59e0b --down #ef4444 --idle #2a2f3a --playhead #ffffff.
- prefers-reduced-motion: no playhead animation; static view with markers.
- Pitch-deck sections: Hero with "See it live →" to RAILWAY_URL (const at top of gantt.js), Operator card
  screenshot placeholder, Evidence (the Gantt), How it works, Footer.
Report files created and how to run (python3 -m http.server 8080 in netlify-visual).
```

## 12. Preguntas abiertas

1. **URL oficial de la demo:** las reglas piden una URL "para evaluación interactiva" y el PLAN la define como Railway en replay. ¿La página de Netlify es un extra (pitch) y la URL que se entrega sigue siendo Railway? Recomendado: sí.
2. **Política Proposed:** ¿qué política (y qué semillas reservadas) se congela para el JSON? Depende de la búsqueda del miércoles.
3. **Calendario:** con UX/UI como última fase, el grabador de intervalos (1–2 h, trabajo del simulador) más las 2 h visuales tienen que caber antes del envío del sábado en la noche. ¿El grabador se adelanta a la fase del simulador (recomendado) aunque la franja se dibuje al final?
4. **Estilo:** pediste "flat flow-diagram" y tu respuesta recomienda Gantt primero. Esta guía hace el **Gantt plano** y deja la vista de flujo como extra. ¿De acuerdo?
