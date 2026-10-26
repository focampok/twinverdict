const RAILWAY_URL = "https://twinverdict.focampo.com";

// Static copies of bench/results/efficiency_20261017.json and
// data/replay/live_c0c92625-de22-4520-accb-6a17c1a76428.json.
const EFFICIENCY_URL = "data/efficiency_20261017.json";
const LIVE_URL = "data/live_c0c92625-de22-4520-accb-6a17c1a76428.json";

const METHOD_ORDER = [
  "regla fija",
  "LLM sin retroalimentación",
  "bucle con retroalimentación",
  "Optuna TPE",
];
const METHOD_LABELS = {
  "regla fija": "Fixed rule",
  "LLM sin retroalimentación": "One-shot LLM",
  "bucle con retroalimentación": "Feedback loop",
  "Optuna TPE": "Optuna",
};
const LOOP_NAME = "bucle con retroalimentación";
const FIXED_NAME = "regla fija";
const OPTUNA_NAME = "Optuna TPE";

const SEEDS = [1000111, 1000104, 1000176];
const DEFAULT_SEED = 1000111;
const PLAY_MS = 12000;
const { WIDTH, LABEL, minutes, downSpans, downUntil } = TwinGantt;

const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const axis = document.querySelector("#axis");
const laneBaseline = document.querySelector("#lane-baseline");
const laneProposed = document.querySelector("#lane-proposed");
const seedSelect = document.querySelector("#seed");
const playButton = document.querySelector("#play");
const jumpButton = document.querySelector("#jump");
const playheadLabel = document.querySelector("#playhead-label");
const seedSummary = document.querySelector("#seed-summary");
const chartError = document.querySelector("#chart-error");

let record = null;
let viewStart = 0;
let viewEnd = 0;
let marker = 0;
let playhead = 0;
let playing = false;
let startedAt = 0;
let playFrom = 0;
let raf = 0;

function wireLinks() {
  const root = RAILWAY_URL.replace(/\/$/, "");
  for (const link of document.querySelectorAll("[data-href='app']")) link.href = root;
  for (const link of document.querySelectorAll("[data-href='live']")) link.href = `${root}/live`;
  for (const link of document.querySelectorAll("[data-href='try']")) {
    link.href = `${root}/#try-policy`;
  }
  for (const link of document.querySelectorAll("[data-href]")) {
    link.target = "_blank";
    link.rel = "noopener noreferrer";
  }
}

function percent(rate) {
  return `${(Math.round(rate * 1000) / 10).toFixed(1)}%`;
}

function objective(value) {
  return Number(value).toFixed(4);
}

function grouped(value) {
  return Math.round(value).toLocaleString("en-US");
}

function finite(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function text(id, value) {
  const node = document.querySelector(id);
  if (node) node.textContent = value;
}

function cell(value, label) {
  const td = document.createElement("td");
  td.className = "num";
  td.dataset.label = label;
  td.textContent = value;
  return td;
}

function renderMethods(report) {
  const body = document.querySelector("#methods-body");
  const byName = new Map((report.methods || []).map((method) => [method.name, method]));
  body.replaceChildren();
  for (const name of METHOD_ORDER) {
    const method = byName.get(name);
    const holdout = method && method.holdout;
    if (!method || !holdout) continue;
    if (finite(holdout.objective) === null || finite(holdout.ci_low) === null || finite(holdout.ci_high) === null) {
      continue;
    }
    const row = document.createElement("tr");
    if (name === LOOP_NAME) row.className = "ours";
    const label = document.createElement("th");
    label.scope = "row";
    label.textContent = METHOD_LABELS[name] || name;
    if (name === LOOP_NAME) {
      const mark = document.createElement("span");
      mark.className = "mark";
      mark.textContent = "on-time result";
      label.append(mark);
    }
    row.append(
      label,
      cell(objective(holdout.objective), "Objective"),
      cell(`[${objective(holdout.ci_low)}, ${objective(holdout.ci_high)}]`, "95% CI"),
      cell(grouped(method.simulations), "Simulations"),
    );
    body.append(row);
  }
}

function renderHonesty(fixed, loop, optuna) {
  const node = document.querySelector("#honesty");
  if (!node || !loop || !optuna) return;
  const loopObj = finite(loop.holdout.objective);
  const optunaObj = finite(optuna.holdout.objective);
  const loopSims = finite(loop.simulations);
  const optunaSims = finite(optuna.simulations);
  const parts = ["These numbers are from the simulated plant."];
  if (loopObj !== null && optunaObj !== null && optunaObj > loopObj && loopSims !== null && optunaSims) {
    const pct = Math.round(((optunaSims - loopSims) / optunaSims) * 100);
    parts.push(
      `Optuna reaches a higher holdout objective (${objective(optunaObj)} versus ${objective(loopObj)}).`,
      `The feedback loop is the policy the model explains in operator language, and it uses ${pct}% fewer simulations (${grouped(loopSims)} versus ${grouped(optunaSims)}).`,
    );
  }
  if (fixed && finite(fixed.holdout.on_time_rate) !== null && finite(loop.holdout.on_time_rate) !== null) {
    parts.push(
      `On-time orders move from ${percent(fixed.holdout.on_time_rate)} to ${percent(loop.holdout.on_time_rate)}.`,
    );
  }
  node.textContent = parts.join(" ");
}

async function loadEfficiency() {
  const status = document.querySelector("#results-status");
  const response = await fetch(EFFICIENCY_URL);
  if (!response.ok) throw new Error(EFFICIENCY_URL);
  const report = await response.json();
  const byName = new Map((report.methods || []).map((method) => [method.name, method]));
  const fixed = byName.get(FIXED_NAME);
  const loop = byName.get(LOOP_NAME);
  const optuna = byName.get(OPTUNA_NAME);
  if (loop && finite(loop.simulations) !== null) text("#hook-sims", grouped(loop.simulations));
  if (fixed && finite(fixed.holdout.on_time_rate) !== null) {
    text("#fixed-ontime", percent(fixed.holdout.on_time_rate));
    text("#ontime-from", percent(fixed.holdout.on_time_rate));
  }
  if (loop && finite(loop.holdout.on_time_rate) !== null) {
    text("#ontime-to", percent(loop.holdout.on_time_rate));
  }
  const seeds = (report.methods || [])
    .map((method) => method.holdout && method.holdout.n_seeds)
    .filter((value) => finite(value) !== null);
  if (seeds.length && seeds.every((value) => value === seeds[0])) {
    text("#holdout-label", `On-time orders. Holdout of ${grouped(seeds[0])} seeds.`);
  }
  renderMethods(report);
  renderHonesty(fixed, loop, optuna);
  if (status) status.hidden = true;
}

function metric(value, label) {
  const block = document.createElement("p");
  block.className = "metric";
  const strong = document.createElement("strong");
  strong.textContent = value;
  const span = document.createElement("span");
  span.textContent = label;
  block.append(strong, span);
  return block;
}

function formatDuration(started, finished) {
  const ms = Date.parse(finished) - Date.parse(started);
  if (!Number.isFinite(ms) || ms < 0) return null;
  const total = Math.round(ms / 1000);
  const min = Math.floor(total / 60);
  const sec = total % 60;
  return `${min} min ${sec} s`;
}

function peak(events, read) {
  let best = null;
  for (const event of events) {
    const value = finite(read(event));
    if (value === null) continue;
    best = best === null ? value : Math.max(best, value);
  }
  return best;
}

async function loadLive() {
  const status = document.querySelector("#amd-status");
  const response = await fetch(LIVE_URL);
  if (!response.ok) throw new Error(LIVE_URL);
  const live = await response.json();
  if (live.model) text("#model-name", live.model);
  const recorded = [live.gpu_name, live.model].filter(Boolean).join(" · ");
  const recordedNode = document.querySelector("#amd-recorded");
  if (recordedNode) {
    recordedNode.textContent = recorded;
    recordedNode.hidden = recorded === "";
  }
  const events = Array.isArray(live.events) ? live.events : [];
  const cards = [];
  const tps = peak(events, (event) => event.vllm && event.vllm.tokens_per_s);
  const running = peak(events, (event) => event.vllm && event.vllm.requests_running);
  const power = peak(events, (event) => event.gpu && event.gpu.power_w);
  const use = peak(events, (event) => event.gpu && event.gpu.use_pct);
  if (tps !== null) {
    cards.push(metric(`${tps.toLocaleString("en-US", { maximumFractionDigits: 1 })} tokens/s`, "Peak tokens per second"));
  }
  if (running !== null) cards.push(metric(grouped(running), "Peak concurrent requests"));
  if (power !== null) cards.push(metric(`${grouped(power)} W`, "Peak power"));
  if (use !== null) cards.push(metric(`${grouped(use)}%`, "Peak GPU use"));
  let firstTokens = null;
  let lastTokens = null;
  for (const event of events) {
    const value = finite(event.vllm && event.vllm.tokens_total);
    if (value === null) continue;
    if (firstTokens === null) firstTokens = value;
    lastTokens = value;
  }
  if (firstTokens !== null && lastTokens !== null) {
    cards.push(metric(grouped(lastTokens - firstTokens), "Tokens this run"));
  }
  const duration = formatDuration(live.started_at, live.finished_at);
  if (duration) cards.push(metric(duration, "Run length"));
  document.querySelector("#amd-metrics").replaceChildren(...cards);
  if (status) status.hidden = true;
}

function renderCounters(root, side) {
  const red = downUntil(downSpans(side.intervals), playhead);
  root.replaceChildren();
  const redBlock = document.createElement("div");
  redBlock.className = "red";
  const redValue = document.createElement("strong");
  redValue.textContent = `${minutes(red)} min`;
  const redLabel = document.createElement("span");
  redLabel.textContent = "Unplanned (red) to playhead";
  redBlock.append(redValue, redLabel);
  const total = document.createElement("div");
  const totalValue = document.createElement("strong");
  totalValue.textContent = `${minutes(side.kpis.unplanned_min)} min`;
  const totalLabel = document.createElement("span");
  totalLabel.textContent = "Unplanned, seed total";
  total.append(totalValue, totalLabel);
  const onTime = document.createElement("div");
  const onTimeValue = document.createElement("strong");
  onTimeValue.textContent = String(Math.round(side.kpis.on_time));
  const onTimeLabel = document.createElement("span");
  onTimeLabel.textContent = "On-time orders, seed total";
  onTime.append(onTimeValue, onTimeLabel);
  root.append(redBlock, total, onTime);
}

function draw() {
  const view = { viewStart, viewEnd, marker, playhead };
  TwinGantt.drawAxis(axis, view);
  TwinGantt.drawLane(laneBaseline, record.policies.baseline.intervals, view);
  TwinGantt.drawLane(laneProposed, record.policies.proposed.intervals, view);
  renderCounters(document.querySelector("#count-baseline"), record.policies.baseline);
  renderCounters(document.querySelector("#count-proposed"), record.policies.proposed);
  playheadLabel.textContent = `Playhead ${minutes(playhead / 60)} h`;
  playButton.textContent = playing ? "Pause" : "Play";
}

function stop() {
  playing = false;
  if (raf) cancelAnimationFrame(raf);
  raf = 0;
}

function frame(now) {
  const span = viewEnd - playFrom;
  const next = playFrom + ((now - startedAt) / PLAY_MS) * (viewEnd - viewStart);
  if (next >= viewEnd || span <= 0) {
    playhead = viewEnd;
    stop();
    draw();
    return;
  }
  playhead = next;
  draw();
  raf = requestAnimationFrame(frame);
}

function play() {
  if (reduced) return;
  if (playing) {
    stop();
    draw();
    return;
  }
  if (playhead >= viewEnd - 1e-6) playhead = viewStart;
  playFrom = playhead;
  startedAt = performance.now();
  playing = true;
  raf = requestAnimationFrame(frame);
}

function jump() {
  stop();
  playhead = marker;
  draw();
}

function seek(svg, event) {
  const point = svg.createSVGPoint();
  point.x = event.clientX;
  point.y = event.clientY;
  const local = point.matrixTransform(svg.getScreenCTM().inverse());
  if (local.x < LABEL) return;
  const fraction = (local.x - LABEL) / (WIDTH - LABEL);
  stop();
  playhead = viewStart + Math.min(1, Math.max(0, fraction)) * (viewEnd - viewStart);
  draw();
}

async function loadSeed(seed) {
  stop();
  chartError.textContent = "";
  const response = await fetch(`data/intervals_${seed}.json`);
  if (!response.ok) throw new Error(`intervals_${seed}.json`);
  record = await response.json();
  const baselineRows = record.policies.baseline.intervals;
  const proposedRows = record.policies.proposed.intervals;
  const window = TwinGantt.divergence(
    baselineRows,
    proposedRows,
    TwinGantt.horizon(baselineRows, proposedRows),
  );
  viewStart = window.viewStart;
  viewEnd = window.viewEnd;
  marker = window.marker;
  playhead = reduced ? marker : viewStart;
  const baseline = record.policies.baseline.kpis;
  const proposed = record.policies.proposed.kpis;
  seedSummary.textContent =
    `Seed ${record.seed}. Unplanned downtime ${minutes(baseline.unplanned_min)} min on the fixed rule and ${minutes(proposed.unplanned_min)} min on the proposed policy. On-time orders ${Math.round(baseline.on_time)} and ${Math.round(proposed.on_time)}.`;
  draw();
}

function fillSeeds() {
  for (const seed of SEEDS) {
    const option = document.createElement("option");
    option.value = String(seed);
    option.textContent = String(seed);
    if (seed === DEFAULT_SEED) option.selected = true;
    seedSelect.append(option);
  }
}

wireLinks();
if (reduced) playButton.disabled = true;
fillSeeds();
playButton.addEventListener("click", play);
jumpButton.addEventListener("click", jump);
laneBaseline.addEventListener("click", (event) => seek(laneBaseline, event));
laneProposed.addEventListener("click", (event) => seek(laneProposed, event));
seedSelect.addEventListener("change", () => {
  loadSeed(seedSelect.value).catch((error) => {
    chartError.textContent = String(error);
  });
});
loadSeed(DEFAULT_SEED).catch((error) => {
  chartError.textContent = String(error);
});
loadEfficiency().catch(() => {
  const status = document.querySelector("#results-status");
  if (status) status.textContent = "The recorded results could not be loaded.";
});
loadLive().catch(() => {
  const status = document.querySelector("#amd-status");
  if (status) status.textContent = "The recorded GPU telemetry could not be loaded.";
});
