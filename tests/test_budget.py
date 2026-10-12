from bench.budget import plan, recommend
from search.config import SearchConfig


def test_budget_recommends_largest_combo_that_fits() -> None:
    sim = {"workers": 4, "parallel_effective_s": 0.001}
    llm = {"rows": [{"concurrency": 32, "valid_per_min": 1000.0}]}
    rows = plan(sim, llm, search=SearchConfig(), sim_workers=4, gpu_price_per_hour=None)
    chosen = recommend(rows)
    assert chosen is not None
    assert (chosen["N"], chosen["K"], chosen["R"]) == (48, 100, 8)
    assert chosen["fits"] is True
    assert chosen["cost_usd"] is None


def test_budget_reports_cost_only_when_price_is_set() -> None:
    sim = {"workers": 4, "parallel_effective_s": 0.001}
    llm = {"rows": [{"concurrency": 8, "valid_per_min": 1000.0}]}
    rows = plan(sim, llm, search=SearchConfig(), sim_workers=4, gpu_price_per_hour=1.99)
    chosen = recommend(rows)
    assert chosen is not None
    assert chosen["cost_usd"] > 0
