"""Plantillas de texto. Sin lógica de búsqueda."""

import json


def propose_messages(context: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Propón una política de mantenimiento y despacho. "
                "Responde solo con JSON que cumpla el esquema Policy."
            ),
        },
        {"role": "user", "content": context},
    ]


def explain_messages(metrics: dict) -> list[dict[str, str]]:
    body = json.dumps(metrics, sort_keys=True, ensure_ascii=False)
    return [
        {
            "role": "system",
            "content": (
                "EXPLAIN_ONLY. Redacta un párrafo corto usando exclusivamente "
                "los números del JSON. No inventes cifras."
            ),
        },
        {"role": "user", "content": body},
    ]
