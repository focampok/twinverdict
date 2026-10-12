"""Evaluación de reglas condicionales. La primera que aplica a la decisión gana."""

from dataclasses import dataclass
from typing import Literal

from policy.schema import Action, Condition, Policy

PM_ACTIONS = frozenset({"POSTPONE_PM", "FORCE_PM"})
DISPATCH_ACTIONS = frozenset({"BATCH_SAME_PRODUCT", "PRIORITIZE_PRODUCT"})


@dataclass(frozen=True, slots=True)
class QueueOrder:
    product: str
    due: float


@dataclass(frozen=True, slots=True)
class DecisionContext:
    machine_id: str
    wear: float
    now: float
    queue: tuple[QueueOrder, ...]
    urgent_slack_min: float


def _urgent(order: QueueOrder, now: float, urgent_slack_min: float) -> bool:
    return (order.due - now) < urgent_slack_min


def condition_matches(cond: Condition, ctx: DecisionContext) -> bool:
    if cond.machine is not None and cond.machine != ctx.machine_id:
        return False
    if cond.wear_gt is not None and not (ctx.wear > cond.wear_gt):
        return False
    if cond.urgent_order_waiting is not None:
        urgent = False
        for order in ctx.queue:
            if _urgent(order, ctx.now, ctx.urgent_slack_min):
                urgent = True
                break
        if urgent != cond.urgent_order_waiting:
            return False
    if cond.queue_len_gt is not None and not (len(ctx.queue) > cond.queue_len_gt):
        return False
    if cond.product_waiting is not None:
        waiting = False
        for order in ctx.queue:
            if order.product == cond.product_waiting:
                waiting = True
                break
        if not waiting:
            return False
    return True


def first_action(
    policy: Policy,
    kind: Literal["pm", "dispatch"],
    ctx: DecisionContext,
) -> Action | None:
    wanted = PM_ACTIONS if kind == "pm" else DISPATCH_ACTIONS
    for rule in policy.rules:
        action = rule.then_
        if action.action not in wanted:
            continue
        if action.action == "FORCE_PM" and action.machine not in (None, ctx.machine_id):
            continue
        if condition_matches(rule.cond, ctx):
            return action
    return None
