const RAILWAY_URL = "";

const SEEDS = [1000111, 1000104, 1000176];
const DEFAULT_SEED = 1000111;
const WINDOW_MIN = 12 * 60;
const STEP_MIN = 15;
const WIDTH = 1000;
const LABEL = 44;
const ROW = 32;
const PLAY_MS = 12000;
const MACHINES = ["M1", "M2", "M3", "M4", "M5"];
const KINDS = new Set(["processing", "setup", "pm", "down", "idle"]);

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
let viewEnd = WINDOW_MIN;
let marker = 0;
let playhead = 0;
let playing = false;
let startedAt = 0;
let playFrom = 0;
let raf = 0;

function bindLive(button, note) {
  if (RAILWAY_URL === "") {
    button.disabled = true;
    note.textContent = "coming soon";
    return;
  }
  button.disabled = false;
  note.textContent = "";
  button.addEventListener("click", () => {
    window.open(RAILWAY_URL, "_blank", "noopener");
  });
}

function percent(rate) {
  return `${(Math.round(rate * 1000) / 10).toFixed(1)}%`;
}

function objective(value) {
  return Number(value).toFixed(4);
}

function minutes(value) {
  return value.toFixed(1);
}

async function fillStory() {
  const response = await fetch("data/story.json");
  if (!response.ok) throw new Error("story.json");
  const story = await response.json();
  const steps = [
    `An LLM on an AMD MI300X (vLLM, ${story.model}) proposes maintenance and dispatch policies as validated JSON.`,
    `The simulator scores them on ${Number(story.n_seeds_holdout)} holdout seeds and reports a 95% confidence interval.`,
    `On time in holdout: ${percent(story.on_time_rate_fixed_holdout)} with the fixed rule, ${percent(story.on_time_rate_best_holdout)} with the best policy.`,
    `Holdout objective, 95% CI: fixed rule ${objective(story.objective_fixed_holdout)} [${objective(story.objective_fixed_holdout_ci_low)}, ${objective(story.objective_fixed_holdout_ci_high)}]; best policy ${objective(story.objective_best_holdout)} [${objective(story.objective_best_holdout_ci_low)}, ${objective(story.objective_best_holdout_ci_high)}].`,
  ];
  const list = document.querySelector("#how-steps");
  list.replaceChildren(
    ...steps.map((text) => {
      const item = document.createElement("li");
      item.textContent = text;
      return item;
    }),
  );
}

function downSpans(intervals) {
  return intervals.filter((row) => row.kind === "down");
}

function overlap(spans, start, end) {
  let sum = 0;
  for (const row of spans) {
    const from = Math.max(row.start, start);
    const to = Math.min(row.end, end);
    if (to > from) sum += to - from;
  }
  return sum;
}

function downUntil(spans, time) {
  return overlap(spans, 0, time);
}

function divergence(baseline, proposed, horizon) {
  const baseDown = downSpans(baseline);
  const proposedDown = downSpans(proposed);
  let bestGap = -Infinity;
  let startAt = 0;
  for (let start = 0; start + WINDOW_MIN <= horizon + 1e-6; start += STEP_MIN) {
    const gap = overlap(baseDown, start, start + WINDOW_MIN) - overlap(proposedDown, start, start + WINDOW_MIN);
    if (gap > bestGap) {
      bestGap = gap;
      startAt = start;
    }
  }
  let peakGap = -Infinity;
  let peak = startAt;
  const windowEnd = startAt + WINDOW_MIN;
  for (let time = startAt; time + 60 <= windowEnd; time += 5) {
    const gap = overlap(baseDown, time, time + 60) - overlap(proposedDown, time, time + 60);
    if (gap > peakGap) {
      peakGap = gap;
      peak = time + 30;
    }
  }
  return { viewStart: startAt, viewEnd: windowEnd, marker: peak };
}

function xOf(time) {
  return LABEL + ((time - viewStart) / (viewEnd - viewStart)) * (WIDTH - LABEL);
}

function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function add(parent, name, attrs) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  parent.appendChild(node);
  return node;
}

function drawAxis() {
  clear(axis);
  add(axis, "rect", { x: 0, y: 0, width: WIDTH, height: 40, fill: "var(--bg)" });
  const markerX = xOf(marker);
  add(axis, "line", {
    x1: markerX,
    x2: markerX,
    y1: 8,
    y2: 40,
    stroke: "var(--pm)",
    "stroke-width": 2,
  });
  const playX = xOf(playhead);
  add(axis, "line", {
    class: "playhead",
    x1: playX,
    x2: playX,
    y1: 18,
    y2: 40,
    stroke: "var(--playhead)",
    "stroke-width": 2,
  });
  const first = Math.ceil(viewStart / 60) * 60;
  for (let time = first; time < viewEnd; time += 60) {
    const x = xOf(time);
    add(axis, "line", { x1: x, x2: x, y1: 28, y2: 40, stroke: "var(--muted)", "stroke-width": 1 });
    const label = add(axis, "text", { x: x + 3, y: 26 });
    label.textContent = `${time / 60} h`;
  }
}

function drawLane(svg, intervals) {
  clear(svg);
  add(svg, "rect", { x: 0, y: 0, width: WIDTH, height: ROW * MACHINES.length, fill: "var(--panel)" });
  for (const [index, machine] of MACHINES.entries()) {
    const y = index * ROW;
    add(svg, "text", { x: 4, y: y + 20 }).textContent = machine;
    for (const row of intervals) {
      if (row.m !== machine || !KINDS.has(row.kind)) continue;
      if (row.end <= viewStart || row.start >= viewEnd) continue;
      const start = Math.max(row.start, viewStart);
      const end = Math.min(row.end, viewEnd);
      const x = xOf(start);
      const width = Math.max(0.4, xOf(end) - x);
      add(svg, "rect", { x, y: y + 4, width, height: ROW - 8, fill: `var(--${row.kind})` });
    }
  }
  const playX = xOf(playhead);
  add(svg, "line", {
    class: "playhead",
    x1: playX,
    x2: playX,
    y1: 0,
    y2: ROW * MACHINES.length,
    stroke: "var(--playhead)",
    "stroke-width": 2,
  });
  const markerX = xOf(marker);
  add(svg, "line", {
    class: "marker",
    x1: markerX,
    x2: markerX,
    y1: 0,
    y2: ROW * MACHINES.length,
    stroke: "var(--pm)",
    "stroke-width": 1.5,
    "stroke-dasharray": "4 3",
  });
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
  drawAxis();
  drawLane(laneBaseline, record.policies.baseline.intervals);
  drawLane(laneProposed, record.policies.proposed.intervals);
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
  const horizon = Math.max(
    ...record.policies.baseline.intervals.map((row) => row.end),
    ...record.policies.proposed.intervals.map((row) => row.end),
  );
  const window = divergence(
    record.policies.baseline.intervals,
    record.policies.proposed.intervals,
    horizon,
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

bindLive(document.querySelector("#live-hero"), document.querySelector("#live-hero-note"));
bindLive(document.querySelector("#live-footer"), document.querySelector("#live-footer-note"));
if (reduced) playButton.disabled = true;
fillSeeds();
fillStory().catch(() => {
  document.querySelector("#how-steps").textContent = "The recorded numbers could not be loaded.";
});
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
