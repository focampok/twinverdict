# TwinVerdict - Arquitectura y alcance (v4)

> Working note, in Spanish. The result judges should use is job `c0c92625-de22-4520-accb-6a17c1a76428`: holdout 1.3691 [1.3530, 1.3842], on time 50.6% → 98.9%, 37,560 simulations. See the repository README and `docs/BENCHMARKS.md`.

**Hackathon:** AMD Developer Hackathon: ACT III · **Track:** Intelligent Industry · **Ventana:** 12 a 18 oct 2026, kickoff lun 12 a las 09:00 GT · **Entrega:** dom 18 oct, 15:00 UTC = **09:00 GT** (confirmado en el dashboard en vivo de lablab) · **Premios:** más de $12,000, incluido un premio opcional de Google de $5,000

**Cambios en v4**
- No se construyó nada el domingo, a propósito: todo arranca desde cero el lun 12 a las 13:00 GT, con el repo de GitHub como primer paso. Calendario de la sección 10 rehecho y comprimido; la primera sesión de GPU pasa al martes en la mañana.
- Hora límite confirmada: dom 18, 09:00 GT. Entrega manual solo hasta 6 h después y con aprobación previa; meta interna: enviar el sábado en la noche.
- Precio de la MI300X incierto ($1.99/h según lablab, $2.59/h según un análisis de 2026): presupuesto con dos escenarios (50 h y 38 h) y qué recortar en el de 38 h.
- Brief de Intelligent Industry y criterios de evaluación: tarjeta de operador como protagonista; URL de demo siempre viva en replay. Premio de Google como decisión opcional del jueves, sin tocar vLLM en AMD.
- Lista de cortes con orden explícito y disparadores más tempranos por el día perdido.

**Cambios en v3 (resumen):** desarrollo nativo en Linux sin docker compose (Postgres del sistema, mock LLM con `uvicorn`, `Makefile`, `honcho`); Docker solo para la imagen de Railway; Postgres administrado de Railway en producción; CI con Postgres como `services:`; worker nativo en la MI300X contra la URL pública de Railway con `sslmode=require`; vLLM en contenedor ROCm en `127.0.0.1` con `--api-key` y túnel SSH.

**Cambios en v2 (resumen):** política con decisiones estructurales (regla de despacho y hasta 5 reglas condicionales); métrica de eficiencia con el mismo presupuesto de simulaciones; simulación en la CPU de la MI300X; polling HTMX con SSE opcional.

## 1. Propuesta

Un gemelo simulado de una línea de producción donde un LLM abierto, servido en una GPU AMD MI300X, **propone políticas** de mantenimiento y despacho. Ninguna política se recomienda sin antes ser **probada en el simulador** sobre cientos de semillas. El número que se reporta lo da el simulador, no el modelo.

**Afirmación a demostrar:** la política encontrada reduce paros no planificados y entregas tardías frente a una regla fija, con intervalo de confianza del 95% sobre semillas no vistas, y llega ahí con menos simulaciones que Optuna (o, si no, se dice).

**Honestidad del alcance:** es una planta simulada, calibrada con un dataset público. No se afirma ningún despliegue real.

## 2. Alcance

| Dentro (MVP) | Fuera |
|---|---|
| Simulador SimPy de 1 línea, 5 máquinas, 3 tipos de producto | Integración con una fábrica real |
| 3 modos de falla con desgaste progresivo | Visión por computador o audio |
| Política en JSON validado: parámetros, regla de despacho y hasta 5 reglas condicionales | Código generado por el LLM |
| Bucle de búsqueda con LLM y 3 líneas base (regla fija, Optuna, LLM sin retroalimentación) | Fine-tuning de modelos |
| UI web con polling HTMX: **tarjeta de operador como pantalla principal**, curva de mejora, comparación, aprobación humana | Autenticación de usuarios |
| Modo `live` (GPU) y modo `replay` (corrida grabada) | Multi-planta, multi-tenant |

**Cortes si falta tiempo:** ver la lista ordenada con disparadores en la sección 10.

**Qué pide el brief de Intelligent Industry:** "un producto funcional, no solo un dashboard", datos industriales realistas que terminen en una alerta o recomendación que un operador entienda, y una mejora medible. Por eso la tarjeta de operador (recomendación + números verificados + aprobar/rechazar) es la primera vista de la UI y el centro del video.

## 3. Arquitectura

```mermaid
flowchart LR
  U[Juez / Operador] --> W[web: FastAPI + HTMX polling]
  W <--> DB[(Postgres en Railway)]
  subgraph GPU[Instancia MI300X - AMD Developer Cloud]
    WK[worker: búsqueda + simulación en CPU] -->|localhost| V[vLLM ROCm]
  end
  WK <-->|TLS| DB
  W -. modo replay .-> DB
  V -. benchmark / rocm-smi .-> W
```

- **web** (Railway): UI, API REST, polling de progreso, endpoint de aprobación, modo replay.
- **worker** (en la instancia MI300X, junto a vLLM, como proceso nativo en un venv de Python): toma trabajos de Postgres (`SELECT ... FOR UPDATE SKIP LOCKED`), orquesta el bucle y simula en paralelo con `ProcessPoolExecutor` usando los núcleos de CPU de la instancia. Habla con vLLM por `localhost`. No se usa Redis. Llega al Postgres de Railway por su **URL pública (proxy TCP) con `sslmode=require`**, no por la red interna de Railway. Si esa conexión da problemas, plan B: escribir resultados en un Postgres local de la instancia (nativo) y sincronizar al final de la corrida.
- **Postgres** (servicio administrado de Railway en producción; Postgres nativo en tu Linux para desarrollo): trabajos, políticas, métricas, corridas grabadas, auditoría.
- **vLLM** (misma instancia): endpoint compatible con OpenAI. Si se expone hacia afuera, solo con API key y TLS.

## 4. Stack

| Capa | Elección | Motivo |
|---|---|---|
| Lenguaje | Python 3.12 | Un solo lenguaje, simulación y servicio |
| Simulación | SimPy 4, NumPy | Eventos discretos, reproducible por semilla |
| Contratos | Pydantic v2 | Valida la política antes de simular |
| API / UI | FastAPI, Jinja2, HTMX (polling), Chart.js | Sin SPA, despliegue simple |
| LLM | vLLM sobre ROCm; modelo abierto en FP8 (elegir el día 1 el que corra estable) | Memoria de 192 GB y alto rendimiento en paralelo |
| Salida | JSON Schema con decodificación guiada | Políticas siempre válidas |
| Cliente LLM | SDK `openai` asíncrono, semáforo de 32 | 32 propuestas en paralelo |
| Línea base | Optuna (TPE) | Pregunta obvia de un juez: "¿por qué un LLM?" |
| Datos | Postgres, SQLAlchemy 2, Alembic | Persistencia y replay |
| Calidad | pytest, ruff, GitHub Actions | CI con LLM simulado (mock) y Postgres como `services:` |
| Entorno local | Linux nativo: Postgres del sistema, `uv`, `Makefile`, `honcho` (`Procfile.dev`) | Sin docker compose; Docker solo para la imagen de Railway |

## 5. Módulos y funciones

1. **`sim/`**: `Plant`, `Machine`, `Order`. KPIs: throughput, % entregas a tiempo, horas de paro no planificado, costo de mantenimiento. Objetivo compuesto con pesos editables.
2. **`sim/calibration.py`**: ajusta la curva desgaste→riesgo de falla con un dataset público de mantenimiento (como AI4I 2020 o C-MAPSS). Documentar qué se calibró y qué no.
3. **`policy/schema.py`**: contrato de la política. Además de los números, el LLM elige la **regla de despacho** y escribe **reglas condicionales** de un vocabulario cerrado (condiciones y acciones enumeradas, máximo 5 reglas, umbrales con rango validado). Es JSON validado con Pydantic, nunca código.
```json
{
  "maintenance": {"pm_wear_threshold": {"M1": 0.70, "M2": 0.65}, "max_pm_per_shift": 1},
  "dispatch": {
    "rule": "CRITICAL_RATIO",
    "weights": {"due_date": 0.6, "wear_risk": 0.3, "setup": 0.1}
  },
  "rules": [
    {"if": {"machine": "M2", "wear_gt": 0.80, "urgent_order_waiting": true},
     "then": {"action": "POSTPONE_PM", "max_minutes": 45}},
    {"if": {"queue_len_gt": 6},
     "then": {"action": "BATCH_SAME_PRODUCT"}}
  ]
}
```
   Reglas de despacho: `EDD`, `SPT`, `WEIGHTED`, `CRITICAL_RATIO`. Acciones: `POSTPONE_PM`, `FORCE_PM`, `BATCH_SAME_PRODUCT`, `PRIORITIZE_PRODUCT`.
4. **`search/loop.py`**: bucle de búsqueda (sección 6).
5. **`llm/client.py`**: proponer políticas, escribir la tarjeta de operador, medir tokens/seg y latencia.
6. **`eval/`**: evaluación en semillas de entrenamiento, reservadas y escenario perturbado; bootstrap del IC; curva de eficiencia.
7. **`baselines/`**: regla fija; Optuna con el mismo presupuesto de simulaciones (ajusta los parámetros numéricos dentro de una estructura de reglas fija y, opcional, la regla de despacho como variable categórica); LLM sin retroalimentación.
8. **`guard/numbers.py`**: verifica que todo número de la tarjeta de operador exista en el diccionario de métricas. Si no, se descarta el texto.
9. **`bench/sim_speed.py`**: mide segundos por simulación y calcula K y N para que una búsqueda quepa en el tiempo objetivo.
10. **`api/`**: `POST /jobs`, `GET /jobs/{id}/status` (polling), `POST /policies/{id}/approve`, `GET /healthz`, `GET /readyz`.
11. **`ui/`**: vistas: escenario, búsqueda en vivo, comparación, tarjeta de operador con aprobar/rechazar, panel de hardware (GPU, tokens/seg).

## 6. Bucle de búsqueda

```text
política_0 = regla fija
para ronda en 1..R (R≈8):
    prompt = escenario + top-k políticas previas con métricas
             + análisis de fallas (paro por máquina, órdenes tardías)
    candidatas = LLM.proponer(N=32, JSON Schema)        # GPU, en paralelo
    válidas = [p para p en candidatas si schema_ok(p)]
    métricas = simular(válidas, K=100 semillas)         # CPU de la instancia MI300X
    actualizar top-k; registrar simulaciones gastadas
mejor = top-1
evaluar(mejor, 300 semillas reservadas + escenario perturbado)
tarjeta = LLM.explicar(métricas)  → guard/numbers → aprobación humana
```

**Costo:** una búsqueda son unas 32 × 100 × 8 ≈ 25,600 simulaciones, más las 300 reservadas y el estrés. Por eso no corre en Railway. El día 1 se mide la velocidad real; si no cabe en 20 a 30 min, se baja K (p. ej. 30 a 50 semillas por ronda, y 100 solo para el top-k) o N.

**Escenario perturbado:** tasa de fallas +30% y pico de demanda. Sirve para ver si la política sobreajustó al simulador.

## 7. Evaluación

- **Comparaciones:** regla fija · Optuna · LLM sin retroalimentación · LLM con bucle, todos con **el mismo presupuesto de simulaciones**.
- **Métrica de eficiencia (definida desde ya):** curva del mejor objetivo encontrado contra simulaciones gastadas, una línea por método. Se reporta cuántas simulaciones necesita cada uno para llegar al 90% (u otro X% fijado antes) del mejor resultado.
- **Métricas finales:** objetivo compuesto y cada KPI, con IC 95% por bootstrap sobre semillas reservadas.
- **Éxito:** el IC de la mejora frente a la regla fija no cruza cero.
- **Si Optuna empata o gana:** el mensaje pasa a "el LLM llega al mismo resultado con menos simulaciones y explica el porqué". No ocultar el resultado.
- **Pruebas:** determinismo por semilla, conservación de órdenes, rechazo de políticas inválidas (incluye más de 5 reglas o umbrales fuera de rango), guard de números.

## 8. Entornos y puesta en producción

### Desarrollo local (Linux nativo, sin docker compose)
- Postgres instalado en el sistema (ya lo tienes). Una sola vez: crear el rol y la base, p. ej. `sudo -u postgres psql -c "CREATE ROLE planta LOGIN PASSWORD 'planta' CREATEDB;"`.
- `.env` con `DATABASE_URL=postgresql+psycopg://planta:planta@localhost:5432/planta` y `LLM_BASE_URL=http://localhost:8001/v1` (mock).
- Targets del `Makefile`: `make setup` (`uv sync`), `make db` (`createdb` si no existe + `alembic upgrade head`, con `DATABASE_URL` de `.env`), `make mock-llm` (uvicorn en 8001), `make web` (uvicorn en 8000), `make worker`, `make dev` (mock + web + worker juntos con `honcho` y `Procfile.dev`), `make test`, `make lint`, `make bench`.
- Docker no se usa para desarrollar.

### CI (GitHub Actions)
- Postgres como `services:` del workflow, con la misma versión mayor que Railway. No depende del entorno local.
- Jobs: lint, tests (con `alembic upgrade head` y tests db) y `docker build` sin push, para verificar que la imagen de Railway compila.

### Railway (solo después de congelar resultados, jueves o después)
- **Servicios:** `web` y el servicio Postgres administrado de Railway. Build con un `Dockerfile` único, que es el **único uso de Docker** en el código del proyecto (aparte, vLLM corre en su contenedor ROCm en la GPU).
- **Imagen:** la misma imagen sirve para `web` y `worker` con distinto comando de arranque. En Railway solo corre `web`; el comando `worker` queda disponible si alguna vez hace falta allí.
- **Config:** `railway.toml` con builder Dockerfile, `startCommand` de web, `healthcheckPath = /healthz` y política de reinicio.
- **Variables:** `DATABASE_URL` como referencia al servicio Postgres (`${{Postgres.DATABASE_URL}}`, red interna), `ADMIN_TOKEN`, `MODE=live|replay`. Nada de claves en el repo. `config.py` normaliza el esquema `postgresql://` de Railway a `postgresql+psycopg://`.
- **Despliegue:** automático desde `main` tras pasar CI. La web es liviana; la CPU pesada ya no está aquí.
- **Verificación de la imagen:** un `docker build` local una vez (o confiar en el job de CI) basta; si prefieres, esa prueba local se pasa al viernes, día del despliegue.

### GPU (AMD Developer Cloud)
- Una instancia MI300X con imagen ROCm. **vLLM corre en su contenedor ROCm** (es la ruta que soporta AMD y la única excepción a "sin contenedores"). El **worker** corre nativo en la misma máquina: clonar el repo, `uv sync`, `uv run python -m worker.main`. Usa `localhost` para vLLM.
- `DATABASE_URL` del worker = URL pública del Postgres de Railway (proxy TCP, la que Railway muestra como `DATABASE_PUBLIC_URL`) con `?sslmode=require`. La red interna de Railway no es alcanzable desde la instancia. Plan B: Postgres local nativo en la instancia y sincronizar resultados al terminar la corrida.
- Si vLLM se expone hacia afuera, va detrás de un proxy TLS (p. ej. Caddy) y con `--api-key`. Nunca exponer el puerto sin clave.
- Se crea solo en sesiones de trabajo y **se destruye al terminar**: una instancia apagada puede seguir cobrando. **Confirma el precio por hora en la consola antes de crearla** (ver sección 9).
- Script `up.sh` para recrearla rápido (instalar `uv`, clonar y `uv sync`, levantar el contenedor de vLLM, arrancar el worker nativo con `nohup` o `tmux`) y no perder tiempo en cada sesión.
- Métricas: `/metrics` de vLLM y `rocm-smi` para el panel de hardware (o captura estática si se aplica el corte 3).

### Modo replay
Cada búsqueda se guarda completa (prompts, candidatas, métricas, latencias, simulaciones gastadas). Con la GPU apagada, `MODE=replay` reproduce una corrida real grabada, **rotulada claramente como REPLAY**. Así quien abra la URL después ve el producto. Las reglas piden la URL de la demo "para evaluación interactiva": un link caído baja la nota de tecnología a cerca de 2/5. La GPU no tiene que estar encendida durante la evaluación; Railway en replay se queda activo hasta que publiquen resultados. El modo `live` se enciende solo en ventanas acordadas para la demo.

### Repo y entrega
- Repo público en GitHub, licencia MIT, **creado el lun 12 después del kickoff** (commits con fecha visible).  En local y sin GPU: con Postgres instalado, `cp .env.example .env`, `make setup`, `make db` (crea la base y aplica `alembic upgrade head`) y `make dev` (mock LLM, web y worker; o por separado con `make mock-llm`, `make web`, `make worker`).
- README: requisitos (Python 3.12, `uv`, Postgres con la misma versión mayor que Railway), variables, cómo correr local, cómo apuntar a un vLLM propio, cómo reproducir resultados.

## 9. Presupuesto de GPU

Saldo: **$100 de créditos AMD Developer Cloud** (facturación de DigitalOcean), vencen el **2 nov 2026**, sin uso todavía. Los créditos se aplican solos al consumo; "Credits applied $0.00" solo significa que aún no hay uso. Método de pago válido en la consola antes de crear la instancia.

**Precio por hora: confirmarlo en la consola antes de crear la instancia.** Lablab dice $1.99/h (unas 50 h con $100); un análisis de precios de 2026 reporta $2.59/h en DigitalOcean (unas 38 h). Anota el precio real en `docs/BENCHMARKS.md` y usa la tabla que corresponda.

**Regla fija:** la instancia se **destruye al terminar cada sesión** (apagarla puede seguir cobrando). Todo el código se escribe y prueba en local contra el mock; la GPU solo se usa para medir, correr búsquedas y grabar.

| Fase | Escenario A: ~50 h ($1.99/h) | Escenario B: ~38 h ($2.59/h) |
|---|---|---|
| Montaje, 2 modelos, smoke JSON y benchmarks (mar) | 5 | 4 |
| Bucle de búsqueda y líneas base en vivo (mar a mié) | 14 | 10 |
| Calibración y ajuste de K y N en la instancia (mié) | 3 | 2 |
| Corridas finales: varias semillas de búsqueda, reservadas y estrés (jue a vie) | 12 | 10 |
| Grabación del video en vivo y capturas de hardware (vie a sáb) | 6 | 4 |
| Reserva | 10 | 8 |
| **Total** | **50** | **38** |

**Qué se recorta en el escenario B (38 h):**
- Iteración del bucle en GPU solo para validar; toda la depuración del bucle se hace en local con el mock.
- Corridas finales: 3 semillas de búsqueda en vez de 5, y Optuna y "LLM sin retroalimentación" corridos en la misma sesión que la búsqueda principal.
- K y N del benchmark tomados por el lado bajo (p. ej. K=50, N=32) si la búsqueda no cabe en 25 min.
- Video: la parte "en vivo" se graba en una sola sesión corta; el resto sale del replay.
- Sin sesiones de GPU "de exploración": cada sesión arranca con una lista escrita de qué medir.

Si el gasto acumulado pasa de $70 antes del viernes, no se abren más sesiones salvo la de corridas finales y grabación.

## 10. Plan (hora de Guatemala)

| Fecha | Objetivo |
|---|---|
| **Dom 11** | Nada de código, a propósito (evitar dudas sobre trabajo previo al kickoff). Solo lectura de reglas. |
| **Lun 12** | Kickoff 09:00 (confirmar dudas). **Desde 13:00, día comprimido y sin GPU:** repo en GitHub (público, MIT) y scaffolding, esquema de la política, simulador v0 con determinismo, `simulate()` y KPIs, mock LLM y `LLMClient`, Postgres nativo con Alembic, worker stub, `Makefile`, CI en verde. Si sobra: scripts `infra/gpu/`, smoke JSON y harness de benchmarks contra el mock. GPU esta noche **solo** si la línea base está completa y el precio está confirmado. |
| **Mar 13** | Mañana: terminar lo que se haya deslizado (scripts GPU, smoke, harness). Primera sesión de GPU: crear instancia, `up.sh`, vLLM con 2 modelos, elegir el estable, smoke JSON, benchmarks de LLM y simulación, fijar K y N. Tarde/noche: arrancar el bucle de búsqueda (local con mock, luego en la instancia). **Hito:** una búsqueda de punta a punta guardada en Postgres. |
| **Mié 14** | Bucle completo, líneas base (regla fija, Optuna, LLM sin retroalimentación) con el mismo presupuesto, persistencia en `runs` para replay, curva de eficiencia, calibración con dataset público. |
| **Jue 15** | UI con polling: **tarjeta de operador primero** (recomendación, números verificados por `guard/numbers`, aprobar/rechazar), curva de mejora y comparación. Corridas finales en la GPU. Decisión sobre el premio de Google (solo si ya hay respuesta en Discord y cabe sin riesgo). |
| **Vie 16** | Evaluación en semillas reservadas y estrés, congelar replay, despliegue en Railway (web + Postgres administrado + `MODE=replay`), README probado en máquina limpia. |
| **Sáb 17** | Video (3 min), portada 16:9, pitch PDF. **Enviar la entrega completa en lablab el sábado en la noche** como margen de seguridad. Última sesión de GPU, si hace falta, y destruir la instancia. |
| **Dom 18** | **09:00 GT: cierre duro.** Solo buffer: revisar que la URL responde y corregir textos. La entrega manual solo se acepta hasta 6 h después y con aprobación previa: no contar con ella. |

**Cortes, en orden (se aplican al primer disparador que se cumpla):**
1. **Lun 22:00:** si no están `simulate()` determinista, el mock y CI en verde, los scripts GPU, el smoke y el harness pasan al mar en la mañana y la GPU arranca el mar al mediodía.
2. **Mar noche:** si el bucle no corre de punta a punta (proponer, validar, simular, guardar), recortar a **3 máquinas** y R=6.
3. **Mié noche:** si las líneas base no están, dejar Optuna solo con parámetros numéricos (sin regla de despacho categórica) y quitar "LLM sin retroalimentación" del video (queda en el README si se corre).
4. **Jue mediodía:** si la UI no tiene la tarjeta de operador funcionando, todo lo demás de la UI se reduce a la tarjeta + curva de eficiencia; el panel de hardware pasa a captura estática del benchmark.
5. **Jue noche:** quitar la vista de UI del escenario de estrés (la evaluación se mantiene en el README y el video). Descartar el premio de Google.
6. **Vie noche:** si Railway falla, la URL de la demo pasa a cualquier hosting simple del modo replay; no se pierde la noche del sábado en infraestructura.
SSE no está en el MVP: solo si sobra tiempo, y no antes del viernes.

**Dudas para el kickoff o el Discord de lablab:**
- ¿Basta el modo replay de una corrida real en la MI300X más el video para cumplir el componente AMD visible para los jueces?
- ¿Qué tecnología de Google cuenta para el premio de $5,000? (No agregar nada de Google antes de tener respuesta.)
- ¿Restricciones de modelos o tamaños?

## 11. Entregables

Título y descripciones, track, etiquetas · portada 16:9 · video MP4 (apuntar a 3 a 5 min) · pitch PDF · repo público · URL de la demo (viva en replay hasta los resultados) · prototipo utilizable.

**Guion del video (3 min), con la tarjeta de operador al centro:** problema y costo del paro, con datos de planta realistas (0:20) · **la tarjeta de operador primero: "qué hacer, cuánto mejora, aprobar"** (0:40) · regla fija como base (0:55) · búsqueda en vivo con 32 propuestas, tokens/seg y GPU AMD (1:35) · curva de eficiencia contra Optuna y solo-LLM, con IC (2:10) · volver a la tarjeta: aprobación humana y alerta concreta (2:35) · estrés, límites y costo por búsqueda (2:55).

**Premio de Google (opcional, baja prioridad):** el mismo proyecto puede competir por el premio principal y el de Google. Solo se considera el jueves, si en Discord aclararon qué tecnología cuenta y si cabe en pocas horas como complemento (p. ej. una pieza periférica). **Nunca reemplaza el componente vLLM en AMD.**

## 12. Riesgos

| Riesgo | Mitigación |
|---|---|
| Día perdido (se arranca el lun 13:00) | Día comprimido sin GPU; prompts con caja de tiempo; cortes con disparadores desde el lunes |
| Precio por hora mayor al anunciado ($2.59 vs $1.99) | Confirmar en consola; tabla de 38 h; desarrollo solo con mock; tope de $70 antes del viernes |
| Créditos vencen el 2 nov o se agotan | Destruir la instancia tras cada sesión; anotar hora de inicio y fin; modo replay |
| Distracción con el premio de Google | Decisión solo el jueves, con respuesta de Discord; nunca toca el núcleo ni vLLM en AMD |
| vLLM sobre ROCm inestable con el modelo elegido | Probar 2 modelos el martes; elegir el estable; fijar el tag exacto de la imagen |
| Optuna gana o empata | Decisiones estructurales en la política; métrica de eficiencia por simulaciones; mensaje honesto |
| Simulación lenta | Benchmark el lunes en local y el martes en la instancia; bajar K; más procesos en la CPU de la instancia |
| Método de pago bloquea crear la instancia | Agregarlo el lunes antes de las 22:00 |
| Entrega tardía o fallo de lablab | Enviar el sábado en la noche; la entrega manual solo 6 h después y con aprobación previa |
| URL de demo caída durante la evaluación (~2/5 en tecnología) | Railway en replay; `/healthz`; revisar la URL el domingo y durante la evaluación |
| "Solo un dashboard" según el brief | Tarjeta de operador con recomendación accionable, aprobación y mejora medible con IC |
| Diferencias entre entorno nativo y Railway | Python 3.12 fijo (`.python-version`, `uv.lock`); misma versión mayor de Postgres en local, CI y Railway; CI construye la imagen |
| Worker en la GPU no llega al Postgres de Railway | URL pública con `sslmode=require`; plan B: Postgres local en la instancia y sincronizar después |
| Simulador "poco realista" | Calibración pública y declaración clara de límites |
| Sobreajuste al simulador | Semillas reservadas y escenario perturbado |
| Alucinación en la tarjeta de operador | `guard/numbers` y texto solo sobre métricas |
