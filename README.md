# twinverdict

Gemelo simulado (SimPy) de una línea de producción con 5 máquinas y 3 productos.
Un LLM propone políticas de mantenimiento y despacho en JSON; el simulador las mide.
Ninguna política se recomienda sin números verificados en muchas semillas.

Plan: `docs/PLAN.md` (v4).

Desarrollo nativo en Linux (Python 3.12, uv, Postgres). Docker solo para la imagen de Railway.
Licencia MIT.

El código de la línea base se escribe durante el hackathon, a partir del lunes 12 de octubre de 2026.
