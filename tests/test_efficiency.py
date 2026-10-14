from eval.efficiency import (
    bootstrap_ci,
    curve,
    improvement_target,
    loop_history,
    sims_to_fraction,
)


def test_curve_is_sorted_and_non_decreasing() -> None:
    history = [
        {"sims_acumuladas": 300, "best_so_far": 0.5},
        {"sims_acumuladas": 100, "best_so_far": 0.2},
        {"sims_acumuladas": 200, "best_so_far": 0.4},
        {"sims_acumuladas": 400, "best_so_far": 0.3},  # baja: manda el máximo corrido
    ]
    points = curve(history)
    bests = [best for _, best in points]
    assert [sims for sims, _ in points] == [100, 200, 300, 400]
    assert bests == [0.2, 0.4, 0.5, 0.5]
    assert bests == sorted(bests)


def test_curve_accepts_the_per_candidate_field_and_collapses_repeats() -> None:
    assert curve([{"sims_acumuladas": 2, "objetivo": 0.7}]) == [(2, 0.7)]
    assert curve(
        [
            {"sims_acumuladas": 5, "best_so_far": 0.1},
            {"sims_acumuladas": 5, "best_so_far": 0.4},
        ]
    ) == [(5, 0.4)]


def test_sims_to_fraction_returns_the_first_crossing_or_none() -> None:
    points = [(10, 0.1), (20, 0.5), (30, 0.9)]
    assert sims_to_fraction(points, 0.1) == 10
    assert sims_to_fraction(points, 0.5) == 20
    assert sims_to_fraction(points, 0.95) is None


def test_improvement_target_sits_above_fixed_by_the_gap_fraction() -> None:
    assert improvement_target(0.25, 1.0) == 0.25 + 0.9 * 0.75
    assert improvement_target(0.25, 1.0, fraction=1.0) == 1.0


def test_fixed_rule_is_a_single_point_that_never_improves() -> None:
    points = curve([{"sims_acumuladas": 180, "best_so_far": 0.2489}])
    assert points == [(180, 0.2489)]
    assert sims_to_fraction(points, 0.5) is None  # plana: no alcanza un umbral mayor
    assert sims_to_fraction(points, 0.2) == 180


def test_loop_history_walks_the_persisted_rounds() -> None:
    payload = {
        "fixed_objective": 0.25,
        "policies": [{"n_seeds": 180}],
        "rounds": [
            {"sims_spent": 360, "evaluated": [{"objective": 0.5}, {"objective": 0.4}]},
            {"sims_spent": 180, "evaluated": [{"objective": 0.9}]},
        ],
    }
    rows = loop_history(payload)
    # Una ronda es un punto: las N candidatas se proponen juntas y luego se simulan.
    assert rows == [
        {"sims_acumuladas": 180, "best_so_far": 0.25},
        {"sims_acumuladas": 540, "best_so_far": 0.5},
        {"sims_acumuladas": 720, "best_so_far": 0.9},
    ]
    assert curve(rows)[-1] == (720, 0.9)


def test_bootstrap_ci_of_a_constant_is_that_constant() -> None:
    assert bootstrap_ci([0.5] * 10) == (0.5, 0.5)


def test_bootstrap_ci_brackets_the_mean() -> None:
    values = [0.1 * index for index in range(20)]
    low, high = bootstrap_ci(values)
    assert low < sum(values) / len(values) < high
