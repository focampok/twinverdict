"""Línea en serie M1..M5. Una semilla, cuatro familias de aleatorios, sin reloj real."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import simpy

from policy.schema import MACHINES, PRODUCTS, Policy
from sim.config import PlantConfig
from sim.dispatch import select_order
from sim.failures import sample_failure
from sim.rules import DecisionContext, QueueOrder, first_action


@dataclass(slots=True)
class Order:
    id: int
    product: str
    product_idx: int
    arrival: float
    due: float
    process_times: tuple[float, ...]
    completed_at: float | None = None


@dataclass(slots=True)
class Machine:
    idx: int
    machine_id: str
    queue: list[Order] = field(default_factory=list)
    wear: float = 0.0
    last_product: str | None = None
    shift: int = -1
    pm_in_shift: int = 0
    postpone_until: float | None = None
    wake: simpy.Event | None = None
    waiting: bool = False


@dataclass(slots=True)
class SimResult:
    orders_created: int
    orders_completed: int
    orders_wip: int
    on_time: int
    unplanned_min: float
    planned_min: float
    maintenance_cost: float
    failures: tuple[int, int, int]
    pm_count: int
    wear_min: float
    wear_max: float
    arrival_times: tuple[float, ...]
    process_times: tuple[tuple[float, ...], ...]


def _rngs(seed: int, n_machines: int = 5):
    root = np.random.SeedSequence(seed)
    arrival_ss, process_ss, failure_ss, repair_ss = root.spawn(4)
    arrival = np.random.Generator(np.random.PCG64(arrival_ss))
    process = np.random.Generator(np.random.PCG64(process_ss))
    failure_children = failure_ss.spawn(n_machines)
    repair_children = repair_ss.spawn(n_machines)
    failures = [np.random.Generator(np.random.PCG64(child)) for child in failure_children]
    repairs = [np.random.Generator(np.random.PCG64(child)) for child in repair_children]
    return arrival, process, failures, repairs


def _generate_orders(
    config: PlantConfig,
    arrival_rng: np.random.Generator,
    process_rng: np.random.Generator,
) -> list[Order]:
    orders: list[Order] = []
    clock = 0.0
    mean_gap = config.arrival_mean_min / config.demand_scale
    mix = np.array(config.product_mix, dtype=float)
    mix = mix / mix.sum()
    sigma = config.process_sigma
    next_id = 0
    while True:
        clock += float(arrival_rng.exponential(mean_gap))
        if clock >= config.horizon_min:
            break
        product_idx = int(arrival_rng.choice(len(PRODUCTS), p=mix))
        slack = float(arrival_rng.uniform(config.slack_low_min, config.slack_high_min))
        times: list[float] = []
        for machine_idx in range(len(MACHINES)):
            mean = config.process_mean[product_idx][machine_idx]
            mu = math.log(mean) - 0.5 * sigma * sigma
            times.append(max(1e-3, float(process_rng.lognormal(mu, sigma))))
        orders.append(
            Order(
                id=next_id,
                product=PRODUCTS[product_idx],
                product_idx=product_idx,
                arrival=clock,
                due=clock + slack,
                process_times=tuple(times),
            )
        )
        next_id += 1
    return orders


def _clamp_wear(machine: Machine, result_bounds: list[float]) -> None:
    if machine.wear < 0.0:
        machine.wear = 0.0
    elif machine.wear > 1.0:
        machine.wear = 1.0
    if machine.wear < result_bounds[0]:
        result_bounds[0] = machine.wear
    if machine.wear > result_bounds[1]:
        result_bounds[1] = machine.wear


def _poke(machine: Machine) -> None:
    if machine.waiting and machine.wake is not None and not machine.wake.triggered:
        machine.wake.succeed()


def _context(machine: Machine, now: float, config: PlantConfig) -> DecisionContext:
    return DecisionContext(
        machine_id=machine.machine_id,
        wear=machine.wear,
        now=now,
        queue=tuple(QueueOrder(order.product, order.due) for order in machine.queue),
        urgent_slack_min=config.urgent_slack_min,
    )


def _should_pm(machine: Machine, policy: Policy, now: float, config: PlantConfig) -> bool:
    shift = int(now // config.shift_min)
    if machine.shift != shift:
        machine.shift = shift
        machine.pm_in_shift = 0
    if machine.pm_in_shift >= policy.maintenance.max_pm_per_shift:
        return False
    action = first_action(policy, "pm", _context(machine, now, config))
    threshold = policy.maintenance.threshold_for(machine.machine_id)  # type: ignore[arg-type]
    worn_out = machine.wear >= threshold
    if action is not None and action.action == "FORCE_PM":
        return True
    if worn_out and action is not None and action.action == "POSTPONE_PM":
        if machine.postpone_until is None:
            machine.postpone_until = now + action.max_minutes
        if now < machine.postpone_until:
            return False
        machine.postpone_until = None
        return True
    if worn_out:
        machine.postpone_until = None
        return True
    return False


def _machine_loop(
    env: simpy.Environment,
    machine: Machine,
    machines: list[Machine],
    policy: Policy,
    config: PlantConfig,
    failure_rng: np.random.Generator,
    repair_rng: np.random.Generator,
    counters: dict[str, float],
    bounds: list[float],
) -> simpy.events.Event:
    horizon = config.horizon_min
    while env.now < horizon - 1e-9:
        if not machine.queue:
            machine.wake = env.event()
            machine.waiting = True
            yield machine.wake
            machine.waiting = False
            continue
        if _should_pm(machine, policy, env.now, config):
            step = min(config.pm_duration_min, horizon - env.now)
            if step <= 1e-9:
                return
            machine.wear = 0.0
            _clamp_wear(machine, bounds)
            machine.pm_in_shift += 1
            counters["pm"] += 1
            counters["planned"] += step
            counters["cost"] += config.pm_cost
            yield env.timeout(step)
            continue
        order = select_order(machine, policy, env.now, config)
        machine.queue.remove(order)
        if machine.last_product not in (None, order.product):
            setup = config.setup_min[machine.idx]
            step = min(setup, horizon - env.now)
            if step <= 1e-9:
                return
            yield env.timeout(step)
            if step + 1e-9 < setup:
                return
        remaining = order.process_times[machine.idx]
        wear_rate = config.wear_per_min[order.product_idx][machine.idx]
        finished = True
        while remaining > 1e-9:
            left = horizon - env.now
            if left <= 1e-9:
                finished = False
                break
            failure = sample_failure(
                failure_rng,
                machine.wear,
                wear_rate,
                remaining,
                config.failure_base_per_min,
                config.failure_midpoint,
                config.failure_steepness,
                config.failure_rate_scale,
            )
            fail_at = None if failure is None else failure[0]
            step = remaining if fail_at is None else min(remaining, fail_at)
            step = min(step, left)
            if step > 1e-12:
                yield env.timeout(step)
                machine.wear += wear_rate * step
                _clamp_wear(machine, bounds)
                remaining -= step
            reached_failure = (
                failure is not None
                and fail_at is not None
                and step + 1e-8 >= fail_at
                and env.now < horizon - 1e-9
            )
            if not reached_failure:
                if remaining > 1e-6:
                    finished = False
                break
            mode_idx = failure[1]
            counters["fail"][mode_idx] += 1
            counters["cost"] += config.repair_cost[mode_idx]
            machine.wear = 0.0
            _clamp_wear(machine, bounds)
            repair = max(1.0, float(repair_rng.exponential(config.repair_mean_min[mode_idx])))
            repair_step = min(repair, max(0.0, horizon - env.now))
            if repair_step > 0.0:
                yield env.timeout(repair_step)
                counters["unplanned"] += repair_step
            if repair_step + 1e-8 < repair or env.now >= horizon - 1e-9:
                finished = False
                break
        if not finished or remaining > 1e-6:
            return
        machine.last_product = order.product
        if machine.idx + 1 < len(machines):
            nxt = machines[machine.idx + 1]
            nxt.queue.append(order)
            _poke(nxt)
        else:
            order.completed_at = env.now
            counters["completed"] += 1
            if order.completed_at <= order.due:
                counters["on_time"] += 1


def run_simulation(policy: Policy, seed: int, config: PlantConfig | None = None) -> SimResult:
    """Corre la planta hasta el horizonte. No toca red, disco ni reloj de pared."""
    cfg = config or PlantConfig()
    arrival_rng, process_rng, failure_rngs, repair_rngs = _rngs(seed, len(MACHINES))
    orders = _generate_orders(cfg, arrival_rng, process_rng)
    env = simpy.Environment()
    machines = [Machine(idx=i, machine_id=MACHINES[i]) for i in range(len(MACHINES))]
    counters: dict[str, float] = {
        "pm": 0.0,
        "planned": 0.0,
        "unplanned": 0.0,
        "cost": 0.0,
        "completed": 0.0,
        "on_time": 0.0,
        "fail": [0, 0, 0],
    }
    bounds = [0.0, 0.0]
    for machine, fail_rng, repair_rng in zip(machines, failure_rngs, repair_rngs, strict=True):
        env.process(
            _machine_loop(
                env, machine, machines, policy, cfg, fail_rng, repair_rng, counters, bounds
            )
        )
    env.process(_source(env, machines[0], orders))
    env.run(until=cfg.horizon_min)
    created = len(orders)
    completed = int(counters["completed"])
    on_time = int(counters["on_time"])
    fails = counters["fail"]
    return SimResult(
        orders_created=created,
        orders_completed=completed,
        orders_wip=created - completed,
        on_time=on_time,
        unplanned_min=float(counters["unplanned"]),
        planned_min=float(counters["planned"]),
        maintenance_cost=float(counters["cost"]),
        failures=(int(fails[0]), int(fails[1]), int(fails[2])),
        pm_count=int(counters["pm"]),
        wear_min=bounds[0],
        wear_max=bounds[1],
        arrival_times=tuple(order.arrival for order in orders),
        process_times=tuple(order.process_times for order in orders),
    )


def _source(env: simpy.Environment, first: Machine, orders: list[Order]):
    for order in orders:
        delay = order.arrival - env.now
        if delay > 0.0:
            yield env.timeout(delay)
        first.queue.append(order)
        _poke(first)
