# Benchmarks

Numbers below were measured. The official comparison is the 16 October 2026 run. Earlier sections keep the plant and the job they were measured on. A higher objective on an older plant is not a better method.

Local measurement date for the first section: 2026-10-12. Local Postgres 16.15.

Public DigitalOcean price on 12 Oct 2026: AMD Instinct MI300X at $2.59/GPU/hour on demand (1 GPU; 20 vCPU, 240 GiB RAM, 192 GB GPU memory). The 8-GPU pack is $20.72/hour. The 12-month reserved plan is $1.91/GPU/hour and does not apply to a droplet destroyed the same day. At $2.59/hour, $100 of credit is about 38 hours. Source: [GPU Droplets Pricing](https://www.digitalocean.com/pricing/gpu-droplets).

## Official result (16 Oct 2026)

Job `c0c92625-de22-4520-accb-6a17c1a76428`. Real vLLM, `Qwen/Qwen3-8B`, AMD Instinct MI300X, calibrated plant (`failure_midpoint` 0.95, `failure_steepness` 18). Profile `default`, seed 1, holdout 300. `started_at` 2026-10-16 18:17:05−06, `finished_at` 18:29:28−06 (**742.9 s**). `llm_source=vllm`, commit `0bfdeef`. **201 valid LLM proposals**, 0 invalid in the freeze, 483 duplicates. `simulations_total` is **37,560** (36,360 of training = 202 policies × 180, plus 1,200 of holdout and stress). The training curve closes at **36,360**.

The fixed rule and Optuna are the calibration-cut runs (same seeds, same plant). The one-shot row is `llm_nofeedback_default_seed1_20261017.json` (`best_objective` 1.2318).

Table printed by `eval.efficiency` from [`bench/results/efficiency_20261017.json`](../bench/results/efficiency_20261017.json). Threshold `0.7858 + 0.9*(1.5188 − 0.7858) = 1.4455`. The holdout interval is a bootstrap of 2,000 resamples with `PCG64(0)`.

| Method | Train | Holdout | 95% CI | On time | Sims | Sims to 90% | Notes |
|---|---:|---:|---|---:|---:|---|---|
| Fixed rule | 0.7858 | 0.7725 | [0.7431, 0.8017] | 50.6% | 180 | does not reach | definitive |
| Optuna TPE | 1.5188 | 1.5126 | [1.5048, 1.5198] | 99.9% | 69,300 | 5,760 | definitive |
| LLM, no feedback | 1.2318 | 1.2259 | [1.2167, 1.2349] | 91.4% | 69,300 | does not reach | real vLLM |
| Feedback loop | 1.3755 | 1.3691 | [1.3530, 1.3842] | 98.9% | 37,560 | does not reach | **official**, real vLLM |

Unrounded JSON: loop training `best_objective` **1.375498030247249** at close (36,360 training sims). Holdout **1.369148246207772**, CI **[1.3530473586435008, 1.3841888015906354]**, on time **0.9891607470550925**. One-shot **1.2317665500868358**. Optuna **1.5188378682250157**. The fixed-rule holdout on-time rate is **0.5057068010861212**. No LLM method crosses the threshold 1.4455373171414716.

Optuna is ahead on the composite objective (holdout 1.5126 against 1.3691) and on on-time delivery (99.9% against 98.9%). It reaches 90% of the gap in 5,760 simulations. The loop’s headline against the fixed rule is **50.6% → 98.9%** on seeds the search did not see. The budgets differ: the loop evaluated 201 valid proposals (37,560 sims); Optuna and the one-shot LLM each used 69,300.

| Simulations | 180 | 8,460 | 13,680 | 20,880 | 25,560 | 36,360 |
|---|---:|---:|---:|---:|---:|---:|
| Loop, best so far | 0.7858 | 1.3670 | 1.3751 | 1.3755 | 1.3755 | 1.3755 |

The operator card (`operator_card_c0c92625-…json`) stores the analytical interval from the job, mean ± 1.96·s/√n: objective **1.3691482462077722**, CI **[1.3537462894545935, 1.3845502029609509]**. That interval is not the bootstrap in the table above. Both describe the same holdout mean. The card’s on-time rates match the JSON: fixed 0.5057068010861212, best 0.9891607470550925.

The winner is `CRITICAL_RATIO` with weights (setup 0.2, due date 0.5, wear risk 0.3), `max_pm_per_shift=1`, empty `pm_wear_threshold`, and 5 rules (`PRIORITIZE_PRODUCT` per machine with `wear_gt` 0.85/0.80/0.75/0.75/0.70). `LLM_MODEL` remains `Qwen/Qwen3-8B`.

Under stress (+30% failures, demand ×1.5) the fixed rule is at 0.1305 on time and the winner at 0.2643. The gap there is throughput (949.9 against 747.9 completed orders).

Telemetry for this job is `data/replay/live_c0c92625-….json` with `fake=false`: 290 samples, 742 seconds, GPU `AMD Instinct MI300X VF`, VRAM 93% throughout, GPU use peak 100% (mean 27%), power peak 570 W (mean 249 W), vLLM token counter 22,003 → 309,085, peak 2,130 tokens/s.

## How to read an objective

Formula (`sim/objective.py`, weights in `sim/objective_weights.json`). Higher is better. It is not clipped to [0, 1]:

`throughput/400 + on_time_rate/1 − unplanned_h/40 − 0.5·planned_h/20 − 0.5·cost/10000`

Holdout seeds are 1,000,001–1,000,300 when `holdout_seeds=300`. They do not overlap the training seeds. Stress reuses those seeds with failures ×1.3 and demand ×1.5. Four extra evaluations (best and fixed, holdout and stress) sit outside the training budget and are added to `simulations_total`.

Optuna does not write conditional rules. The LLM may write up to five. That is the structural difference. It is not, by itself, a higher score.

## Monday 12, local machine

- Hardware: Intel Core Ultra 7 255H, 16 cores, 1 thread per core, x86_64.
- Command: `uv run python -m bench.sim_speed --seeds 100 --workers 16`.
- Serial: mean 0.1038 s, p95 0.1386 s per simulation.
- Parallel, time inside each process: mean 0.1582 s, p95 0.2356 s.
- Parallel, wall clock with 16 workers: 1.144 s for 100 simulations, 0.0114 s per simulation.
- A search of K=100, N=32, R=8 (25,600 simulations) fits in 4.88 min on these 16 cores.
- In 25 min, about 131,000 simulations at that rate.
- One core, at the serial rate (0.1038 s), would take about 44 min for those 25,600 simulations.
- About 4 cores are enough to get under 25 min if scaling matches this measurement (16 cores × 4.88 / 25 ≈ 3.1, rounded up).

The mock LLM on the same machine (`bench.llm_throughput --concurrency 8,16,32,64 --n 64`) had a valid rate of 1.0. The best pace was 16 in parallel, about 58,700 valid policies per minute. That number is the mock, not vLLM. `bench.budget` with `SIM_WORKERS=16` and no `GPU_PRICE_PER_HOUR` recommends N=48, K=100, R=8 in 7.44 min. The defaults in `search/config.py` stayed at N=32, K=100, R=8 until the MI300X was measured. The mock does not limit the search. The GPU can.

## Tuesday 13, MI300X

- Model: `Qwen/Qwen3-8B`.
- Image: DigitalOcean vLLM 0.27.1 1-Click. Container and Docker image `rocm`. vLLM started with `docker exec` and `--api-key`. Server fingerprint: `vllm-0.27.1-71b87f10`.
- Cores on the instance: 20 (`nproc`). The simulation below did not run there.
- Price for this session: $1.99/hour (about 50 h on $100). Docker published port 8000 on `0.0.0.0`. The API key was required. The measured path was the SSH tunnel to `127.0.0.1:8000`.
- `bench.llm_smoke --n 20` against the schema in `policy/schema.py` (`response_format` json_schema strict): 20/20 valid, rate 1.000. p50 4.372 s, p95 5.259 s, 570.1 output tokens per second. The client sent all 20 at once (concurrency 32).
- `bench.llm_throughput --concurrency 1,8,32 --n 64` (64/64 valid at all three levels):

  | Conc | Valid/min | tok/s | p50 s | p95 s |
  |---:|---:|---:|---:|---:|
  | 1 | 65.8 | 175.1 | 0.8731 | 1.6029 |
  | 8 | 310.5 | 821.4 | 1.3401 | 2.4921 |
  | 32 | 796.5 | 2267.5 | 1.8544 | 3.3896 |

- `bench.sim_speed --seeds 100 --workers 16` on this laptop (16 cores, the same machine as Monday): serial mean 0.0909 s, p95 0.1137 s. Parallel, time inside the process: mean 0.1741 s, p95 0.2897 s. Wall clock: 1.206 s for 100 simulations, 0.0121 s per simulation.
- `bench.budget` with `GPU_PRICE_PER_HOUR=1.99`: the harness grid (N in 16/32/48, K in 30/50/100, R in 6/8) fits inside 25 min. The largest cell is N=48, K=100, R=8 in 8.32 min (39,000 simulations, $0.28). That is under the 20–30 min window, so K was raised outside the grid.
- Chosen combination: **N=48, K=300, R=8** (23.8 min). Calculation with 796.5 valid policies per minute at concurrency 32 and 0.012056 s per simulation (16 workers):
  - Proposals: 48 × 8 = 384. LLM time: 384 / 796.5 = 0.48 min.
  - Simulations: 48 × 300 × 8 = 115,200 of training, plus 300 reserved and 300 of stress = 115,800.
  - Simulation time: 115,800 × 0.012056 / 60 = 23.27 min.
  - Total: 0.48 + 23.27 = 23.8 min. GPU cost at $1.99/h: 23.8 / 60 × 1.99 = $0.79.
  - The clock is the simulation. Raising K from 100 to 300 spends the window on more seeds per policy. N=48 is the top of the grid. R=8 is the plan’s top. With `SIM_WORKERS=2` the simulation leg stretches ×8 and leaves the window.
- Start time, end time, and session cost: the instance was already destroyed. The repo does not have the end time or the closed cost.

## Qwen3-32B, same session

Switched with `infra/gpu/gpu.sh serve Qwen/Qwen3-32B` and `wait`, before the instance was destroyed. The client sends `chat_template_kwargs.enable_thinking=false`. Without that, one of 20 requests to the 32B did not finish (two attempts, ~50 tokens/s with no stop). The 8B measurement above used default thinking. Guided JSON still closed on its own.

- `bench.llm_smoke --n 20`: 17/20 valid, rate 0.850. p50 1.598 s, p95 2.660 s, 425.0 output tokens per second. The 3 invalid replies have `rule=WEIGHTED` and no `weights`. The guided schema leaves them optional. Pydantic requires them.
- `bench.llm_throughput --concurrency 1,8,32 --n 64`:

  | Conc | Valid/min | tok/s | p50 s | p95 s | Valid |
  |---:|---:|---:|---:|---:|---:|
  | 1 | 48.2 | 49.2 | 0.8762 | 1.8249 | 55/64 |
  | 8 | 275.5 | 281.2 | 1.1111 | 2.4059 | 56/64 |
  | 32 | 634.2 | 675.0 | 2.0813 | 3.7793 | 56/64 |

### 8B against 32B

Same laptop for simulation (0.0121 s per simulation, 16 workers). Concurrency 32:

| | 8B | 32B |
|---|---:|---:|
| Valid JSON (smoke, n=20) | 100% | 85% |
| Valid/min | 796.5 | 634.2 |
| tok/s | 2267.5 | 675.0 |
| p50 s | 1.8544 | 2.0813 |
| p95 s | 3.3896 | 3.7793 |

With N=48, K=300, R=8 the LLM asks for 384 valid policies. The 8B takes 0.48 min. The 32B takes 384 / 634.2 = 0.61 min. Simulation stays at 23.27 min. The total moves from 23.8 to 23.9 min. N, K, and R stay put: the clock is still the simulation. The 8B produces more tokens per second and stays at or above 0.95 valid JSON, so it remains the default `LLM_MODEL`. The 32B is judged on policy quality, not tokens per second.

## Validation, job 78fea53a

Job `78fea53a-be2d-4bf5-98a3-e9a12b6cba83`, mock, base scenario. Postgres: `started_at` 2026-10-13 17:27:33−06, `finished_at` 18:08:22−06, **2448.5 s (40.8 min)**, 115,500 simulations, 385 policies (1 fixed rule + 384 from the LLM, 48/48 valid in all 8 rounds). Search seeds: 1–300. The job did not run holdout (`params` has no `holdout`; `metrics` only has `seed_set=train`). The best policy appears in round 5.

The simulator was not changed. No conservation bug, seed bug, or maintenance-off bug showed up, so there is no new regression test.

### Training objective and each KPI

Means over the 300 search seeds. The terms rebuild the stored objective (0.236458 and 0.957665). The interval on the row is the one the job stored: mean ± 1.96·s/√n, not the bootstrap further down.

| | Fixed rule | Best (round 5) |
|---|---:|---:|
| Objective | 0.2365 (0.2058, 0.2671) | 0.9577 (0.9440, 0.9714) |
| Throughput (orders completed) | 736.16 | 822.49 |
| On time | 0.4591 | 0.9852 |
| Unplanned downtime (h) | 20.58 | 12.24 |
| Planned downtime (h) | 20.77 | 32.49 |
| Maintenance cost | 20,586 | 19,313 |
| Orders created | 839.51 | 839.51 |
| WIP | 103.35 | 17.02 |
| Failures | 46.05 | 27.73 |
| Preventive maintenances | 103.86 | 162.50 |

| Term | Weight | Fixed | Best | Difference |
|---|---:|---:|---:|---:|
| throughput / 400 | 1 | 1.8404 | 2.0562 | +0.2158 |
| on time | 1 | 0.4591 | 0.9852 | +0.5261 |
| − unplanned downtime / 40 | 1 | −0.5145 | −0.3060 | +0.2085 |
| − 0.5 · planned downtime / 20 | 0.5 | −0.5193 | −0.8122 | −0.2929 |
| − 0.5 · cost / 10000 | 0.5 | −1.0293 | −0.9656 | +0.0637 |
| Sum | | 0.2365 | 0.9577 | +0.7212 |

The jump is mostly **on time** (0.46 → 0.99, +0.53 of the +0.72). Throughput and less unplanned downtime add about +0.21 each. Planned downtime pushes the other way: the winner does more preventive work.

The throughput reference is 400 and the line completes about 740–820 orders, so that term is worth ~2 and lifts both policies. The fixed rule sits at 0.24 because it is late and piles up WIP.

The winner is WEIGHTED (weights due date 0.423, setup 0.093, wear risk 0.484), `max_pm_per_shift=2`, thresholds M3=0.95, M4=0.92, M5=0.83. M1 and M2 are absent from the JSON and use the default threshold 0.75. The fixed rule is EDD, threshold 0.75 on all five machines, one preventive stop per shift. The winner does more preventive work (162 against 104) and more planned downtime (32.5 h against 20.8 h). It does not win by turning maintenance off.

`orders_created` is the same for both (839.51). On each seed, created = completed + WIP. Demand does not depend on the policy.

### Holdout and stress

Holdout: seeds 1,000,001–1,000,300. Intersection with 1–300: empty. Stress uses the same seeds, failures ×1.3 and demand ×1.5. 95% CI by bootstrap of the per-seed objective: 2,000 resamples, `numpy.random.Generator(PCG64(0))`, percentiles 2.5 and 97.5 of the mean. Order conservation: 0 failures in the four evaluations. `orders_created` matches across policies (holdout 838.83, stress 1259.12).

| | Objective | 95% CI | On time | Throughput | Unplanned downtime (h) |
|---|---:|---:|---:|---:|---:|
| Fixed, holdout | 0.2483 | (0.2175, 0.2773) | 0.4625 | 737.04 | 20.55 |
| Best, holdout | 0.9579 | (0.9439, 0.9715) | 0.9868 | 822.20 | 12.31 |
| Fixed, stress | −0.3210 | (−0.3392, −0.3029) | 0.1259 | 738.56 | 24.76 |
| Best, stress | −0.0693 | (−0.0942, −0.0464) | 0.2744 | 955.87 | 22.10 |

On holdout the gap holds (+0.71) and on time carries it again (+0.52). Under stress both go negative: demand rises to 1,259 orders and WIP stays high (521 fixed, 303 winner). The gap falls to +0.25 and the large term is throughput (955.9 against 738.6). The winner stays ahead. The intervals do not cross in either scenario.

### Workers and the 40 minutes

`jobs.params` has no `workers`. `_run_search` leaves `workers=None` and `run_search` uses `Settings().SIM_WORKERS`. The `.env` of this run has `SIM_WORKERS=16`. At the code default (2) and the in-process time of a burst (~0.17 s), 115,500 simulations would be about 2.7 h. The job took 40.8 min, which matches 16 workers at the sustained rate below.

Job clock: 2448.5 / 115,500 = **0.0212 s per simulation**. The same day’s benchmark (100 seeds, one pool) was **0.0121 s**. Repeat on the afternoon of 13 Oct, fixed rule, 300 seeds, 16 workers:

| Batch | Wall clock | Time inside the process | Effective s/sim |
|---|---:|---:|---:|
| First new pool | 3.39 s | 0.174 s | 0.0113 |
| New pools 2–6 | ~7.2 s | ~0.37 s | ~0.024 |
| Six batches on an already open pool | ~7.1 s | ~0.35 s | ~0.024 |

The first batch reproduces the benchmark. From the second, time inside the process doubles (0.17 s → 0.37 s) and the wall clock follows. A shared pool does not shorten the batch: `ProcessPoolExecutor` startup is not the gap. Postgres writes one `metrics` row per policy when the job closes (385 rows, round events between 18:08:21 and 18:08:22), not one write per simulation.

16 cores at 0.34 s internal give 300 × 0.34 / 16 = 6.4 s per policy. The job did 2448.5 / 385 = 6.36 s per policy. The parallel pool was busy. The extra time against the expected 24 min is the sustained frequency of the Core Ultra 7 255H. A 100-seed burst fits in turbo. A 40-minute job does not. No small code change returns the 0.0121 s while the CPU stays loaded.

### K for 20 to 30 minutes

At the job’s rate (0.0212 s/sim) and with 385 policies (1 + 48×8, all valid, as in this run):

| K | Simulations | Minutes |
|---:|---:|---:|
| 150 | 57,750 | 20.4 |
| 180 | 69,300 | 24.5 |
| 200 | 77,000 | 27.2 |
| 300 | 115,500 | 40.8 |

**Default K: 180** (profile `default` in `search/config.py`). N and R stay at 48 and 8.

- Profile `default`, K=180: 385 × 180 × 0.0212 = 1469 s = **24.5 min**.
- Profile `final`, K=300: 385 × 300 × 0.0212 = 2448 s = **40.8 min**. That is the long run if time remains at the end. N, R, and the rest match the default.
- Profile `smoke`: N=2, K=2, R=2, TOP_K=2, holdout 0. Tests use it. It is not a search budget.

On the laptop, `SIM_WORKERS=16` is required. `SearchConfig.from_profile("final")` and `from_profile("smoke")` build those two profiles. `SearchConfig()` is the default.

## Wednesday 14, Optuna

Optuna (TPE) baseline with the same budget as the loop: `K + N*R*K`. Profile `default` (N=48, K=180, R=8) is **69,300** training simulations, seeds `range(1, 181)`, scenario `base`. Trial 0 is `fixed_rule_policy()`, the same as policy 0 of the loop. `SIM_WORKERS=16`. Code: `baselines/optuna_search.py`, commit `d2c7243`. Command: `uv run python -m baselines.optuna_search --profile default --seed 1`.

Search space, using the ranges in `policy/schema.py`: `pm_wear_threshold` per machine (0.30–0.95), `max_pm_per_shift` (0–3), dispatch rule in {EDD, SPT, WEIGHTED, CRITICAL_RATIO}, and, when the rule is WEIGHTED, the three weights (normalized to sum 1 by the schema). `rules` is empty. Optuna does not write conditional rules.

| Method | Simulations | Best objective | Fixed rule | Trials | Min |
|---|---:|---:|---:|---:|---:|
| Optuna TPE | 69,300 | 1.0061 | 0.2489 | 385 | 13.1 |

Best-so-far curve, from the JSON `history`:

| Simulations | 180 | 8,640 | 17,280 | 34,560 | 51,840 | 69,300 |
|---|---:|---:|---:|---:|---:|---:|
| Best so far | 0.2489 | 0.9886 | 0.9948 | 0.9995 | 1.0061 | 1.0061 |

Almost all of the value lands in the first 8,640 simulations. The winning policy is `CRITICAL_RATIO`, `max_pm_per_shift=2`, thresholds between 0.734 and 0.828 per machine, no rules. No trial was invalid (`failed_trials=0`).

On the clock: 786 s for 69,300 simulations is **0.0113 s/sim** sustained with 16 workers, close to the 0.0121 s of Monday’s short series and far from the 0.0212 s/sim of job `78fea53a` (40.8 min), which is the basis of the 24.5 min estimate above. The simulator did not change between the two measurements, and no code change was measured that explains the factor of 1.9. It stays as an open discrepancy. Methods are compared by simulation count, not by the minute.

This table has no holdout. The budget is training, and it is the same by definition, so comparing inside it favors every method the same way. The four-method table is the next section.

## Wednesday 14, LLM with no feedback

The LLM proposes `N*R` policies from one fixed prompt, without seeing objectives, KPIs, or the top-k of earlier rounds. Same budget and same training seeds as a search of the profile: `default` (N=48, K=180, R=8) → **69,300** simulations, seeds `range(1, 181)`, scenario `base`, `SIM_WORKERS=16`. Sampling seeds match the loop (`rng_seed + batch*10_000`), so the only intended variable is the prompt text. Code: `baselines/llm_nofeedback.py`, commit `726e653`. Command: `uv run python -m baselines.llm_nofeedback --profile default --seed 1` against the local mock.

| Method | Simulations | Best objective | Fixed rule | Valid | Min |
|---|---:|---:|---:|---:|---:|
| LLM, no feedback | 69,300 | 0.9592 | 0.2489 | 384/384 | 15.6 |
| Optuna TPE (section above) | 69,300 | 1.0061 | 0.2489 | — | 13.1 |

The two rows share K, the 180 seeds, the scenario, and the budget. On that yardstick Optuna leads the one-shot LLM by 0.047.

Best-so-far curve, from the JSON `history`:

| Simulations | 180 | 8,820 | 17,460 | 34,740 | 43,380 | 69,300 |
|---|---:|---:|---:|---:|---:|---:|
| Best so far | 0.2489 | 0.9009 | 0.9009 | 0.9206 | 0.9592 | 0.9592 |

Almost all of the jump is in the first batch. From the fifth batch to the eighth, nothing moves. The winning policy is `WEIGHTED` with weights (0.423, 0.484, 0.093), thresholds M3=0.95, M4=0.92, M5=0.83, `max_pm_per_shift=2`, and one rule (`queue_len_gt=4 → BATCH_SAME_PRODUCT`). No proposal was invalid.

**What this number does not measure.** Against the mock, this baseline cannot be separated from the loop. The mock derives each policy from the `seed` and never reads the prompt (`llm/mock_server.py`: `_seed_from` looks at `body["seed"]` and `generate_policy(seed)` ignores the messages). With the same sampling seeds, the 384 candidates are the same set the loop would see, and the best objective matches by construction. 0.9592 is the ceiling of 384 mock draws, not a measure of feedback. That comparison needs vLLM, which does read the prompt. It is repeated in GPU session 2.

On the clock: 15.6 min with 16 workers (0.0135 s/sim), between Optuna’s 0.0113 s/sim and job `78fea53a`’s 0.0212 s/sim.

## Wednesday 14, efficiency curve

Best objective found against simulations spent, one curve per method, all on the same training budget (profile `default`, K=180, seeds `range(1, 181)`, scenario `base`). The threshold was fixed **before** looking at the results, on the improvement, not on the raw objective (which is not bounded to 0–1):

`target = fixed + 0.9 * (best_global - fixed) = 0.2489 + 0.9*(1.0061 - 0.2489) = 0.9303`

Code: `eval/efficiency.py`, commit `efd808a`. The loop search for this profile and seed was run fresh (`search.loop --seed 1 --holdout 0`). Job `78fea53a` is K=300 and was not comparable. `--holdout 0` was used because those seeds are added to `simulations_total` and would break the equal budget.

| Method | Best train | Holdout | 95% CI | On time, holdout | Sims spent | Sims to 90% | Notes |
|---|---:|---:|---|---:|---:|---:|---|
| Fixed rule | 0.2489 | 0.2483 | [0.2175, 0.2773] | 46.2% | 180 | does not reach | definitive |
| Optuna TPE | 1.0061 | 0.9906 | [0.9779, 1.0031] | 99.6% | 69,300 | 3,060 | definitive |
| LLM, no feedback | 0.9592 | 0.9579 | [0.9439, 0.9715] | 98.7% | 69,300 | 43,380 | mock, not a measure of the LLM |
| Feedback loop | 0.9592 | 0.9579 | [0.9439, 0.9715] | 98.7% | 69,300 | 43,380 | mock, not a measure of the LLM |

Holdout: the 300 seeds from 1,000,001, with a 95% CI by bootstrap of 2,000 resamples and `PCG64(0)`. That is 4 × 300 = 1,200 simulations **outside** the search budget. On-time rate is recomputed from each method’s stored `best_policy`.

Cross-check with Tuesday’s validation, which was left untouched: the fixed rule is 46.2% on time with CI [0.2175, 0.2773] and the loop policy is 98.7% with [0.9439, 0.9715], against the (0.218, 0.277) and (0.944, 0.972) already in this file. The holdout and bootstrap pipeline reproduces those numbers.

**What this table can support.** The definitive comparison here is the fixed rule against Optuna, because neither goes through the LLM. Optuna wins on the 180 training seeds (1.0061 against 0.2489) and on holdout (0.9906 against 0.2483), and it reaches the threshold in **3,060** simulations against 43,380 for the one-shot LLM and the loop.

The two LLM rows are **the same number by construction**. The curves match point for point (9 points, the same values). The mock derives each policy from the seed and does not read the prompt, and both runs use the same sampling seeds, so the 384 candidates are the same set and the batch order matches the round order. What that equality measures is the ceiling of 384 mock draws, not what feedback adds. The measured comparison is **TPE against random search**: 1.0061 against 0.9592, and 3,060 against 43,380 simulations. TPE leads by 0.047 with about fourteen times fewer simulations.

The LLM’s structural advantage — up to 5 conditional rules, which Optuna never writes — cannot be judged with the mock. The mock’s winner uses one rule (`queue_len_gt=4 → BATCH_SAME_PRODUCT`) and still loses. That says 384 draws do not beat TPE. It says nothing about rules written by an LLM. Each JSON declares `config.llm_source` (`search/repro.py` derives it from the endpoint and the mock port). `--llm-source` is only an override for old JSON files.

Curve granularity is the granularity at which the method can act on information. Per trial in Optuna (each trial sees the previous ones, 385 points), per round or batch in the loop and the no-feedback LLM (the N candidates are proposed together and then simulated, 9 points; one point per candidate would flatter the loop), and a single point for the fixed rule, extended horizontally to the budget. At that granularity, “sims to 90%” for the one-shot and the loop is quantized to batches of 8,640 simulations, so the crossing falls on a batch boundary.

JSON with the four curves: `bench/results/efficiency_20261014.json` (local; most of `bench/results` is gitignored). The figure is Chart.js. matplotlib was not added.

## Wednesday 14, calibration with AI4I 2020

Wear → risk curve fitted with AI4I 2020 (UCI 601, 10,000 rows, downloaded 2026-10-14, sha256 `dc6630cd…c8a8e`). The full account of what was fitted and what was assumed is [`docs/CALIBRATION.md`](CALIBRATION.md). This section keeps the numbers.

Labeled as wear failure: TWF ∪ OSF (141 records), the two AI4I modes that appear only at high wear. HDF, PWF, and RNF are flat across the range and are the background.

| Parameter | Before | After (AI4I) |
|---|---:|---:|
| `failure_midpoint` | 0.72 | 0.9500 |
| `failure_steepness` | 14.0 | 18.0 |
| `failure_base_per_min` | (0.0015, 0.0012, 0.0018) | **unchanged** (see below) |

**The per-minute level was not calibrated.** AI4I has no duration per record, so there is no data-backed conversion from per-record probability to a per-minute rate. The parameter stays an assumption, marked in `sim/calibrated_params.json` (`level_calibrated: false`).

Impact, same policy, 100 holdout seeds (1,000,001–1,000,100), scenario `base`. `uv run python -m bench.calibration_impact`:

| Policy | Config | Objective | On time | Failures | Unplanned downtime (h) |
|---|---|---:|---:|---:|---:|
| Fixed rule | default | 0.2275 | 44.7% | 45.74 | 20.3614 |
| Fixed rule | calibrated | 0.7424 | 48.6% | 27.30 | 12.4468 |
| Best of the loop | default | 0.9480 | 98.4% | 27.56 | 12.3640 |
| Best of the loop | calibrated | 1.4047 | 99.2% | 4.58 | 1.9679 |

The card’s **on-time rate holds**: 44.7% → 48.6% and 98.4% → 99.2%. The story “46% → 99%” did not depend on the calibration. The two “default” rows reproduce Tuesday’s validation on 100 of the 300 seeds (44.7% against 46.3%, 98.4% against 98.7%).

The composite objective moves a lot (0.948 → 1.4047). **That is not a better method.** The objective is not bounded to 0–1 and the throughput term has weight, so a gentler plant scores higher. **Objectives from two different plant configs are not comparable.** Efficiency tables above this section were measured at midpoint 0.72 and steepness 14. The “calibrated” rows here already use 0.95 and 18, but that shape was not yet the default. The cut that adopts it is next.

## Wednesday 14, GPU session 2 (Qwen3-8B, vLLM)

Plant from before the cut: `failure_midpoint` 0.72, `failure_steepness` 14. These objectives are not compared with the calibration-cut section.

`make gpu2` with profile `default`, seed 1, holdout 300, `SIM_WORKERS=16`, and `LLM_MODEL=Qwen/Qwen3-8B` through the tunnel `http://127.0.0.1:8000/v1`. The loop is job `4c3fe819-b308-45f0-870d-407854e9f02e`: `started_at` 2026-10-14 14:02:17−06, `finished_at` 14:20:15−06 (1078 s). `llm_source=vllm`, commit `0d94141`. 384/384 valid proposals, 0 invalid. `simulations_total` is **70,500** because it adds the 1,200 of holdout and stress (4 × 300). The training curve closes at **69,300**, the same budget as Optuna and the one-shot. The fixed rule and Optuna in this table are Wednesday’s local runs. The one-shot was also 384/384 valid.

Table printed by `eval.efficiency` (`bench/results/efficiency_20261014.json`, threshold `0.2489 + 0.9*(1.0061 − 0.2489) = 0.9303`). Holdout CI is the bootstrap of 2,000 resamples with `PCG64(0)`.

| Method | Train | Holdout | 95% CI | On time | Sims | Sims to 90% | Notes |
|---|---:|---:|---|---:|---:|---|---|
| Fixed rule | 0.2489 | 0.2483 | [0.2175, 0.2773] | 46.2% | 180 | does not reach | definitive |
| Optuna TPE | 1.0061 | 0.9906 | [0.9779, 1.0031] | 99.6% | 69,300 | 3,060 | definitive |
| LLM, no feedback | 0.8274 | 0.8384 | [0.8239, 0.8531] | 83.2% | 69,300 | does not reach | real vLLM |
| Feedback loop | 0.8712 | 0.8772 | [0.8657, 0.8885] | 89.9% | 70,500 | does not reach | real vLLM |

Unrounded JSON: one-shot `best_objective` **0.827404935352991** from batch 1 (8,820 simulations) through 69,300. Loop `best_objective` **0.8712105287438211** from round 1 (8,820) through 69,300. Neither crosses the threshold 0.930344254218952.

| Simulations | 180 | 8,820 | 17,460 | 69,300 |
|---|---:|---:|---:|---:|
| One-shot, best so far | 0.2489 | 0.8274 | 0.8274 | 0.8274 |
| Loop, best so far | 0.2489 | 0.8712 | 0.8712 | 0.8712 |

Loop holdout on the card (`operator_card_4c3fe819-…json`): objective 0.8771740180657116, CI stored by the job [0.8656651043782586, 0.8886829317531646], on time 0.899415303204306. The winner is SPT, `max_pm_per_shift=2`, empty `pm_wear_threshold`, 5 rules. The one-shot winner is WEIGHTED with weights (0.25, 0.5, 0.25), the same `max_pm_per_shift=2`, empty thresholds, 5 rules. This session has no 32B policy-quality run in `bench/results`. `LLM_MODEL` stays `Qwen/Qwen3-8B`.

## Calibration cut (14 Oct 2026)

`PlantConfig` adopts the AI4I shape: `failure_midpoint` 0.95, `failure_steepness` 18. `failure_base_per_min` does not change. `calibrated_plant_config()` matches that default. **Objectives in this section are not compared with the sections above.** A 1.52 here and a 1.01 in the GPU 2 table do not say which method wins. The plant is a different one.

`make gpu2` with profile `default`, seed 1, holdout 300, `SIM_WORKERS=16`, and `LLM_MODEL=Qwen/Qwen3-8B` through the tunnel `http://127.0.0.1:8000/v1`. The loop is job `2fa98c9c-40c4-4f50-8313-b1049d66a9b1`: `started_at` 2026-10-14 16:53:35−06, `finished_at` 17:12:59−06 (1164 s). `llm_source=vllm`, commit `b0fd30e`. 384/384 valid proposals, 0 invalid. `simulations_total` is **70,500** because it adds the 1,200 of holdout and stress (4 × 300). The training curve closes at **69,300**. The fixed rule and Optuna are the local runs of the cut (Optuna: 16.1 min, 385 trials, 0 failed). The Optuna JSON declares `failure_midpoint` 0.95 and `failure_steepness` 18. The one-shot was also 384/384 valid.

Table printed by `eval.efficiency` (`bench/results/efficiency_20261014.json`, threshold `0.7858 + 0.9*(1.5188 − 0.7858) = 1.4455`). Holdout CI is the bootstrap of 2,000 resamples with `PCG64(0)`.

| Method | Train | Holdout | 95% CI | On time | Sims | Sims to 90% | Notes |
|---|---:|---:|---|---:|---:|---|---|
| Fixed rule | 0.7858 | 0.7725 | [0.7431, 0.8017] | 50.6% | 180 | does not reach | definitive |
| Optuna TPE | 1.5188 | 1.5126 | [1.5048, 1.5198] | 99.9% | 69,300 | 5,760 | definitive |
| LLM, no feedback | 1.2318 | 1.2259 | [1.2167, 1.2349] | 91.4% | 69,300 | does not reach | real vLLM |
| Feedback loop | 0.7858 | 0.7725 | [0.7431, 0.8017] | 50.6% | 70,500 | does not reach | real vLLM |

Unrounded JSON: fixed rule and loop **0.7858323573895744** from policy 0 through 69,300. One-shot `best_objective` **1.2317665500868358** from batch 6 (52,020 simulations). Optuna **1.5188378682250157**. No LLM method crosses the threshold 1.4455373171414716.

| Simulations | 180 | 8,820 | 34,740 | 52,020 | 69,300 |
|---|---:|---:|---:|---:|---:|
| One-shot, best so far | 0.7858 | 1.1514 | 1.1953 | 1.2318 | 1.2318 |
| Loop, best so far | 0.7858 | 0.7858 | 0.7858 | 0.7858 | 0.7858 |

Loop holdout on the card (`operator_card_2fa98c9c-…json`): objective 0.7725039817047121, CI stored by the job [0.7429516383465712, 0.8020563250628531], on time 0.5057068010861212. Those three numbers, and the rest of the train, holdout, and stress KPIs, match the fixed rule (`delta_on_time` 0). The policy stored as best is EDD, `max_pm_per_shift=1`, empty `pm_wear_threshold`, 0 rules. The one-shot winner is WEIGHTED with weights (0.4, 0.35, 0.25), `max_pm_per_shift=2`, thresholds 0.65/0.70/0.75/0.80/0.85, and 5 rules. `LLM_MODEL` stays `Qwen/Qwen3-8B`.

**This loop row is not official.** The job stayed on the fixed rule (a top-k clone bug, fixed in `476e8cf`). The next two sections are the calibrated-plant loop runs. The official one is the 16 October section at the top of this file.

## Wednesday 14, GPU session 4 (calibrated plant; superseded)

Calibrated-plant loop (`failure_midpoint` 0.95, `failure_steepness` 18). This was the official run until the telemetry session (`c0c92625…`, at the top of this file). Compare these objectives with the calibration-cut section (same plant), not with GPU 2 or with the midpoint-0.72 tables.

Profile `default`, seed 1, holdout 300, `SIM_WORKERS=16`, `LLM_MODEL=Qwen/Qwen3-8B` through the tunnel `http://127.0.0.1:8000/v1`. The loop is job `285d1787-5d7c-464a-9897-4c585663f088`: `started_at` 2026-10-14 18:28:47−06, `finished_at` 18:44:07−06 (**919.5 s**). `llm_source=vllm`, commit `476e8cf`. Of 300 proposals with a validation result, **262 valid and 38 invalid** (round 2 alone contributed 34; see the note below). `simulations_total` is **48,540** (47,340 of training = 263 policies × 180, plus 1,200 of holdout and stress). The training curve closes at **47,340**, not 69,300: fewer policies were valid than the N×R ceiling. The fixed rule and Optuna are the cut’s runs. The one-shot in the table is the calibrated-plant vLLM run (384/384 valid, `best_objective` 1.2318).

Table printed by `eval.efficiency` (`bench/results/efficiency_20261015.json`, threshold `0.7858 + 0.9*(1.5188 − 0.7858) = 1.4455`). Holdout CI is the bootstrap of 2,000 resamples with `PCG64(0)`.

| Method | Train | Holdout | 95% CI | On time | Sims | Sims to 90% | Notes |
|---|---:|---:|---|---:|---:|---|---|
| Fixed rule | 0.7858 | 0.7725 | [0.7431, 0.8017] | 50.6% | 180 | does not reach | definitive |
| Optuna TPE | 1.5188 | 1.5126 | [1.5048, 1.5198] | 99.9% | 69,300 | 5,760 | definitive |
| LLM, no feedback | 1.2318 | 1.2259 | [1.2167, 1.2349] | 91.4% | 69,300 | does not reach | real vLLM |
| Feedback loop | 1.3810 | 1.3863 | [1.3705, 1.4014] | 98.8% | 48,540 | does not reach | real vLLM (superseded) |

Unrounded JSON: loop `best_objective` **1.3809907221951065** at close (47,340 training sims). One-shot **1.2317665500868358**. Optuna **1.5188378682250157**. No LLM method crosses the threshold 1.4455373171414716. The loop leads the one-shot by 0.15 in training and 0.16 in holdout. Optuna stays ahead on the objective (1.52 against 1.38) and reaches the threshold in 5,760 sims.

| Simulations | 180 | 8,280 | 25,200 | 31,860 | 37,440 | 41,940 | 47,340 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Loop, best so far | 0.7858 | 1.3565 | 1.3631 | 1.3686 | 1.3766 | 1.3768 | 1.3810 |

| Simulations | 180 | 8,820 | 26,100 | 34,740 | 52,020 | 69,300 |
|---|---:|---:|---:|---:|---:|---:|
| One-shot, best so far | 0.7858 | 1.0992 | 1.1514 | 1.1953 | 1.2318 | 1.2318 |

Loop holdout on the card (`operator_card_285d1787-…json`): objective 1.3862772356985602, CI stored by the job [1.3709379596738258, 1.4016165117232946], on time **0.9884149935550874**. Fixed rule on the same holdout: 0.5057068010861212 on time. That card’s headline was **50.6% → 98.8%**. Under stress (+30% failures, demand ×1.5) the fixed rule is at 0.1305 on time and the best at 0.4528. The gap there is throughput (965.3 against 747.9).

The winner is `CRITICAL_RATIO` with weights (setup 0.3, due date 0.3, wear risk 0.4), `max_pm_per_shift=1`, empty `pm_wear_threshold`, and 5 rules (`PRIORITIZE_PRODUCT` per machine with `wear_gt` 0.95/0.94/0.93/0.96/0.92). The one-shot winner is still the cut’s WEIGHTED policy. `LLM_MODEL` stays `Qwen/Qwen3-8B`.

### Note: round 2 of 285d1787 (34 invalid)

In **round 2** of that job (15 valid, **34 invalid**) almost every failure was the same Pydantic check: `rules.*.if` with `machine: null` and `product_waiting: null`. The official run (`c0c92625…`) does not repeat that problem (201 valid LLM proposals).

Historical artifacts for this superseded run stay in the repo as `operator_card_285d1787-…json` and `replay_285d1787-…json`. They are not what the demo serves.
