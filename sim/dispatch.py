"""Despacho de la cola de una máquina. Menor costo sale primero; empate por id de orden."""

from __future__ import annotations

from typing import TYPE_CHECKING

from policy.schema import Policy
from sim.config import PlantConfig
from sim.rules import DecisionContext, QueueOrder, first_action

if TYPE_CHECKING:
    from sim.model import Machine, Order


def _cost(order: Order, machine: Machine, policy: Policy, now: float, config: PlantConfig) -> float:
    weights = policy.dispatch.weights
    assert weights is not None
    slack = order.due - now
    process = order.process_times[machine.idx]
    setup_penalty = 0.0 if machine.last_product in (None, order.product) else 1.0
    wear_frac = config.wear_per_min[order.product_idx][machine.idx] / config.wear_scale()
    rule = policy.dispatch.rule
    if rule == "EDD":
        return order.due
    if rule == "SPT":
        return process
    if rule == "CRITICAL_RATIO":
        remaining = 0.0
        for index in range(machine.idx, len(order.process_times)):
            remaining += order.process_times[index]
        ratio = slack / remaining if remaining > 0.0 else slack
        return (
            weights.due_date * ratio
            + weights.wear_risk * wear_frac * 100.0
            + weights.setup * setup_penalty * 50.0
        )
    return (
        weights.due_date * slack
        + weights.wear_risk * wear_frac * config.horizon_min
        + weights.setup * setup_penalty * 30.0
    )


def select_order(machine: Machine, policy: Policy, now: float, config: PlantConfig) -> Order:
    snapshot = tuple(QueueOrder(order.product, order.due) for order in machine.queue)
    ctx = DecisionContext(
        machine_id=machine.machine_id,
        wear=machine.wear,
        now=now,
        queue=snapshot,
        urgent_slack_min=config.urgent_slack_min,
    )
    action = first_action(policy, "dispatch", ctx)
    pool = machine.queue
    if action is not None and action.action == "BATCH_SAME_PRODUCT":
        if machine.last_product is not None:
            same = [order for order in pool if order.product == machine.last_product]
            if same:
                pool = same
    elif action is not None and action.action == "PRIORITIZE_PRODUCT":
        preferred = [order for order in pool if order.product == action.product]
        if preferred:
            pool = preferred
    best = pool[0]
    best_key = (_cost(best, machine, policy, now, config), best.id)
    for order in pool[1:]:
        key = (_cost(order, machine, policy, now, config), order.id)
        if key < best_key:
            best = order
            best_key = key
    return best
