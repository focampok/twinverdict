// Drawing shared by the static page (gantt.js) and the app's "Try a policy" panel.
// Colors live in gantt.css; this file only references the CSS variables.
const TwinGantt = (() => {
  const WINDOW_MIN = 12 * 60;
  const STEP_MIN = 15;
  const WIDTH = 1000;
  const LABEL = 44;
  const ROW = 32;
  const MACHINES = ["M1", "M2", "M3", "M4", "M5"];
  const KINDS = new Set(["processing", "setup", "pm", "down", "idle"]);

  function minutes(value) {
    return value.toFixed(1);
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

  function horizon(baseline, proposed) {
    return Math.max(...baseline.map((row) => row.end), ...proposed.map((row) => row.end));
  }

  function divergence(baseline, proposed, end) {
    const baseDown = downSpans(baseline);
    const proposedDown = downSpans(proposed);
    let bestGap = -Infinity;
    let startAt = 0;
    for (let start = 0; start + WINDOW_MIN <= end + 1e-6; start += STEP_MIN) {
      const gap =
        overlap(baseDown, start, start + WINDOW_MIN) - overlap(proposedDown, start, start + WINDOW_MIN);
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

  function xOf(view, time) {
    return LABEL + ((time - view.viewStart) / (view.viewEnd - view.viewStart)) * (WIDTH - LABEL);
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

  function drawAxis(svg, view) {
    clear(svg);
    add(svg, "rect", { x: 0, y: 0, width: WIDTH, height: 40, fill: "var(--bg)" });
    const markerX = xOf(view, view.marker);
    add(svg, "line", { x1: markerX, x2: markerX, y1: 8, y2: 40, stroke: "var(--pm)", "stroke-width": 2 });
    if (view.playhead !== null) {
      const playX = xOf(view, view.playhead);
      add(svg, "line", {
        class: "playhead",
        x1: playX,
        x2: playX,
        y1: 18,
        y2: 40,
        stroke: "var(--playhead)",
        "stroke-width": 2,
      });
    }
    const first = Math.ceil(view.viewStart / 60) * 60;
    for (let time = first; time < view.viewEnd; time += 60) {
      const x = xOf(view, time);
      add(svg, "line", { x1: x, x2: x, y1: 28, y2: 40, stroke: "var(--muted)", "stroke-width": 1 });
      const label = add(svg, "text", { x: x + 3, y: 26 });
      label.textContent = `${time / 60} h`;
    }
  }

  function drawLane(svg, intervals, view) {
    clear(svg);
    add(svg, "rect", { x: 0, y: 0, width: WIDTH, height: ROW * MACHINES.length, fill: "var(--panel)" });
    for (const [index, machine] of MACHINES.entries()) {
      const y = index * ROW;
      add(svg, "text", { x: 4, y: y + 20 }).textContent = machine;
      for (const row of intervals) {
        if (row.m !== machine || !KINDS.has(row.kind)) continue;
        if (row.end <= view.viewStart || row.start >= view.viewEnd) continue;
        const start = Math.max(row.start, view.viewStart);
        const end = Math.min(row.end, view.viewEnd);
        const x = xOf(view, start);
        const width = Math.max(0.4, xOf(view, end) - x);
        add(svg, "rect", { x, y: y + 4, width, height: ROW - 8, fill: `var(--${row.kind})` });
      }
    }
    if (view.playhead !== null) {
      const playX = xOf(view, view.playhead);
      add(svg, "line", {
        class: "playhead",
        x1: playX,
        x2: playX,
        y1: 0,
        y2: ROW * MACHINES.length,
        stroke: "var(--playhead)",
        "stroke-width": 2,
      });
    }
    const markerX = xOf(view, view.marker);
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

  return {
    WIDTH,
    LABEL,
    minutes,
    downSpans,
    downUntil,
    horizon,
    divergence,
    drawAxis,
    drawLane,
  };
})();
