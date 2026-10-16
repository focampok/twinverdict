const RAILWAY_URL = "";

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
