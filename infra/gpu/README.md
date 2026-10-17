# GPU session (AMD Developer Cloud, MI300X)

1. Create the instance in the console. Write down the hourly price and the start time before confirming.
2. `ssh` to the instance, copy `infra/gpu/.env.gpu` (never into the repo), run `./infra/gpu/up.sh`, then `./infra/gpu/vllm.sh start`.
3. Tunnel from local Linux: `ssh -N -L 8000:127.0.0.1:8000 user@IP`. vLLM is at `http://127.0.0.1:8000/v1` and is not exposed to the internet. From the repo, `infra/gpu/gpu.sh serve`, `wait`, and `tunnel` do the same steps. See the repository README.
4. Harness benchmarks (`bench.llm_smoke`, `bench.llm_throughput`, `bench.sim_speed`, `bench.budget`).
5. Close: copy results (`scp` of `docs/BENCHMARKS.md`, or `git push`), `./infra/gpu/vllm.sh stop`, and destroy the instance in the console. Powering it off is not enough: it can keep billing. Write down the end time and the estimated cost.
