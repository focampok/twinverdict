"""Servidor mock compatible con OpenAI. Devuelve políticas válidas y deterministas."""

from __future__ import annotations

import hashlib
import json
import os

import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from policy.schema import MACHINES, PRODUCTS, parse_policy

app = FastAPI(title="TwinVerdict mock LLM")

_DISPATCH = ("EDD", "SPT", "WEIGHTED", "CRITICAL_RATIO")
_NEEDS_WEIGHTS = frozenset({"WEIGHTED", "CRITICAL_RATIO"})


def _seed_from(body: dict) -> int:
    if body.get("seed") is not None:
        return int(body["seed"])
    messages = body.get("messages") or []
    blob = json.dumps(messages, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(blob.encode()).hexdigest()
    return int(digest[:8], 16)


def _rule(rng: np.random.Generator) -> dict:
    kind = int(rng.integers(0, 4))
    if kind == 0:
        machine = MACHINES[int(rng.integers(0, len(MACHINES)))]
        wear = round(float(rng.uniform(0.50, 0.99)), 2)
        minutes = int(rng.integers(15, 241))
        return {
            "if": {"machine": machine, "wear_gt": wear},
            "then": {"action": "POSTPONE_PM", "max_minutes": minutes},
        }
    if kind == 1:
        machine = MACHINES[int(rng.integers(0, len(MACHINES)))]
        return {
            "if": {"machine": machine, "queue_len_gt": int(rng.integers(1, 11))},
            "then": {"action": "FORCE_PM", "machine": machine},
        }
    if kind == 2:
        return {
            "if": {"queue_len_gt": int(rng.integers(1, 21))},
            "then": {"action": "BATCH_SAME_PRODUCT"},
        }
    product = PRODUCTS[int(rng.integers(0, len(PRODUCTS)))]
    return {
        "if": {"product_waiting": product},
        "then": {"action": "PRIORITIZE_PRODUCT", "product": product},
    }


def generate_policy(seed: int) -> dict:
    rng = np.random.Generator(np.random.PCG64(seed))
    rule = _DISPATCH[int(rng.integers(0, len(_DISPATCH)))]
    thresholds: dict[str, float] = {}
    for machine in MACHINES:
        if float(rng.random()) < 0.8:
            thresholds[machine] = round(float(rng.uniform(0.30, 0.95)), 2)
    dispatch: dict = {"rule": rule}
    if rule in _NEEDS_WEIGHTS or float(rng.random()) < 0.5:
        raw = rng.random(3) + 0.05
        total = float(raw.sum())
        dispatch["weights"] = {
            "due_date": float(raw[0] / total),
            "wear_risk": float(raw[1] / total),
            "setup": float(raw[2] / total),
        }
    n_rules = int(rng.integers(0, 6))
    policy = {
        "version": 1,
        "maintenance": {
            "pm_wear_threshold": thresholds,
            "max_pm_per_shift": int(rng.integers(0, 4)),
        },
        "dispatch": dispatch,
        "rules": [_rule(rng) for _ in range(n_rules)],
    }
    parse_policy(policy)
    return policy


def _completion(content: str, model: str, prompt_tokens: int, completion_tokens: int) -> dict:
    return {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _explain(body: dict) -> str:
    messages = body.get("messages") or []
    user = ""
    for message in messages:
        if message.get("role") == "user":
            user = message.get("content") or ""
    try:
        metrics = json.loads(user)
    except json.JSONDecodeError:
        metrics = {}
    parts = []
    if isinstance(metrics, dict):
        for key in sorted(metrics):
            value = metrics[key]
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                parts.append(f"{key}={value}")
    if not parts:
        return "Sin números verificados en el contexto."
    return "Resultado verificado: " + ", ".join(parts) + "."


@app.get("/v1/models")
def models() -> dict:
    return {
        "object": "list",
        "data": [{"id": "mock", "object": "model", "owned_by": "twinverdict"}],
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> JSONResponse:
    body = await request.json()
    model = str(body.get("model") or "mock")
    messages = body.get("messages") or []
    explain = any("EXPLAIN_ONLY" in (message.get("content") or "") for message in messages)
    if explain:
        text = _explain(body)
        return JSONResponse(
            _completion(text, model, prompt_tokens=20, completion_tokens=max(1, len(text) // 4))
        )
    seed = _seed_from(body)
    rate = float(os.environ.get("MOCK_INVALID_RATE", "0") or 0)
    rng = np.random.Generator(np.random.PCG64(seed))
    if rate > 0 and float(rng.random()) < rate:
        content = "{esto no es json"
        return JSONResponse(_completion(content, model, prompt_tokens=30, completion_tokens=4))
    policy = generate_policy(seed)
    content = json.dumps(policy, ensure_ascii=False)
    tokens = max(1, len(content) // 4)
    return JSONResponse(_completion(content, model, prompt_tokens=40, completion_tokens=tokens))
