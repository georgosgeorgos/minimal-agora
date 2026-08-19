from __future__ import annotations

import json
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from minimal_agora.analysis import (
    _get_nested,
    compute_statistics,
    extract_field_timelines,
    load_trajectories,
)


class DashboardHandler(SimpleHTTPRequestHandler):
    run_dir: Path
    runs_root: Path
    fields: list[str]
    populations: list[str]
    score_fields: list[str]

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            self._serve_html()
        elif path == "/api/data":
            self._serve_data()
        elif path == "/api/runs":
            self._serve_runs()
        elif path == "/api/stream":
            self._serve_sse()
        else:
            self.send_error(404)

    def _serve_html(self):
        html = _build_html()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html.encode())

    def _resolve_run_dir(self) -> Path:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        run_name = params.get("run", [None])[0]
        if run_name and self.runs_root:
            candidate = self.runs_root / run_name
            if candidate.is_dir():
                return candidate
        return self.run_dir

    def _serve_data(self):
        run_dir = self._resolve_run_dir()
        data = _collect_data(run_dir, self.fields, self.populations, self.score_fields)
        data["run_dir"] = run_dir.name
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_runs(self):
        runs = _list_runs(self.runs_root, self.run_dir)
        body = json.dumps(runs).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        last_count = 0
        try:
            while True:
                data = _collect_data(self.run_dir, self.fields, self.populations, self.score_fields)
                count = data.get("n_trajectories", 0)
                if count != last_count:
                    msg = f"data: {json.dumps(data)}\n\n"
                    self.wfile.write(msg.encode())
                    self.wfile.flush()
                    last_count = count
                time.sleep(2)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, format, *args):
        pass


def _list_runs(runs_root: Path, current_run_dir: Path) -> list[dict]:
    runs = []
    if not runs_root or not runs_root.is_dir():
        return [{"dirname": current_run_dir.name, "scenario": current_run_dir.name,
                 "n_trajectories": 0, "current": True}]
    for d in sorted(runs_root.iterdir()):
        if not d.is_dir():
            continue
        traj_dirs = list(d.glob("trajectory_*"))
        scenario = d.name
        for td in traj_dirs[:1]:
            tj = td / "trajectory.json"
            if tj.exists():
                try:
                    meta = json.loads(tj.read_text())
                    scenario = meta.get("scenario_name", d.name)
                except (json.JSONDecodeError, OSError):
                    pass
                break
        runs.append({
            "dirname": d.name,
            "scenario": scenario,
            "n_trajectories": len(traj_dirs),
            "current": d.resolve() == current_run_dir.resolve(),
        })
    return runs


def _collect_data(
    run_dir: Path, fields: list[str], populations: list[str], score_fields: list[str],
) -> dict:
    trajectories = load_trajectories(run_dir)
    if not trajectories:
        return {"n_trajectories": 0, "outcomes": {}, "steps": {}, "timelines": {}, "populations": {}}

    outcomes: dict[str, int] = {}
    steps_by_outcome: dict[str, list[int]] = {}
    all_fitness: list[list[float | None]] = []

    for t in trajectories:
        cls = t.outcome.classification if t.outcome else "unclassified"
        outcomes[cls] = outcomes.get(cls, 0) + 1
        steps_by_outcome.setdefault(cls, []).append(len(t.steps))
        if "fitness_history" in t.metadata:
            all_fitness.append(t.metadata["fitness_history"])

    n = len(trajectories)
    outcome_data = {
        k: {"count": v, "rate": v / n, "mean_steps": _mean(steps_by_outcome.get(k, []))}
        for k, v in outcomes.items()
    }

    timelines = {}
    trajectory_timelines: dict[str, dict[str, list[dict]]] = {}
    if fields:
        raw = extract_field_timelines(trajectories, fields)
        for field, step_data in raw.items():
            series = []
            for step_num in sorted(step_data.keys()):
                vals = [v for v in step_data[step_num] if isinstance(v, (int, float))]
                if vals:
                    stats = compute_statistics(vals)
                    series.append({"step": step_num, **stats})
            timelines[field] = series

        for field in fields:
            trajectory_timelines[field] = {}
            for t in trajectories:
                tid = str(t.trajectory_id)
                pts = []
                for step in t.steps:
                    val = _get_nested(step.state_after, field)
                    if isinstance(val, (int, float)):
                        pts.append({"step": step.step_number, "value": val})
                if pts:
                    trajectory_timelines[field][tid] = pts

    pop_data: dict[str, Any] = {}
    if populations and score_fields:
        for pop in populations:
            pop_data[pop] = {}
            for sf in score_fields:
                field = f"populations.{pop}.{sf}"
                raw_pop = extract_field_timelines(trajectories, [field])
                series = []
                for step_num in sorted(raw_pop.get(field, {}).keys()):
                    vals = [v for v in raw_pop[field][step_num] if isinstance(v, (int, float))]
                    if vals:
                        series.append({"step": step_num, "mean": _mean(vals), "min": min(vals), "max": max(vals)})
                pop_data[pop][sf] = series

    fitness_data = []
    if all_fitness:
        max_len = max(len(h) for h in all_fitness)
        for i in range(max_len):
            raw_vals = [h[i] for h in all_fitness if i < len(h)]
            fit_vals: list[int | float] = [v for v in raw_vals if v is not None]
            if fit_vals:
                fitness_data.append({"step": i, "mean": _mean(fit_vals), "min": min(fit_vals), "max": max(fit_vals)})

    events = _collect_events(trajectories, run_dir)

    return {
        "scenario": trajectories[0].scenario_name,
        "n_trajectories": n,
        "outcomes": outcome_data,
        "timelines": timelines,
        "trajectory_timelines": trajectory_timelines,
        "populations": pop_data,
        "fitness": fitness_data,
        "events": events,
    }


def _collect_events(trajectories: list, run_dir: Path) -> list[dict]:
    events = []

    for t in trajectories:
        tid = t.trajectory_id
        for step in t.steps:
            if step.resolution and step.resolution.narrative:
                events.append({
                    "trajectory": tid,
                    "step": step.step_number,
                    "type": "narrative",
                    "text": step.resolution.narrative,
                })

            delta_keys = set(step.resolution.state_delta.keys()) if step.resolution else set()
            for p in step.proposals:
                accepted = bool(delta_keys & set(p.proposed_changes.keys())) if delta_keys else False
                if p.reasoning:
                    events.append({
                        "trajectory": tid,
                        "step": step.step_number,
                        "type": "proposal",
                        "agent": p.agent,
                        "text": p.reasoning,
                        "accepted": accepted,
                        "proposed_fields": list(p.proposed_changes.keys()),
                    })

        # Check for wildcards in board directory
        traj_dir = run_dir / f"trajectory_{tid:03d}"
        if traj_dir.exists():
            for wc_file in sorted(traj_dir.glob("board/wildcard_step_*.json")):
                try:
                    with open(wc_file) as f:
                        wc = json.load(f)
                    step_num = int(wc_file.stem.split("_")[-1])
                    events.append({
                        "trajectory": tid,
                        "step": step_num,
                        "type": "wildcard",
                        "name": wc.get("name", "unknown"),
                        "text": f"{wc.get('name', 'unknown')}: {wc.get('description', '')[:150]}",
                    })
                except (ValueError, OSError, KeyError):
                    pass

        if t.outcome:
            events.append({
                "trajectory": tid,
                "step": t.outcome.final_step,
                "type": "outcome",
                "text": f"Trajectory {tid} classified as: {t.outcome.classification}",
            })

    events.sort(key=lambda e: (e["trajectory"], e["step"]))
    return events


def _mean(vals: list) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _build_html() -> str:
    return """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>minimal-agora dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3"></script>
<style>
  :root[data-theme="dark"] {
    --bg: #0a0a0a; --card-bg: #141414; --card-bg-alt: #1a1a1a;
    --text: #e0e0e0; --text-heading: #fff; --text-muted: #888; --text-secondary: #aaa;
    --text-tertiary: #ccc; --border: #222; --border-light: #333;
    --grid: #222; --tooltip-bg: rgba(20,20,20,0.95); --tooltip-border: #333;
    --event-gradient-end: #141414; --event-bg-alt: #0f0f0f;
    --status-live-bg: #1a3a1a; --status-done-bg: #1a2a3a;
    --crosshair: rgba(255,255,255,0.12);
  }
  :root[data-theme="light"] {
    --bg: #f5f5f5; --card-bg: #fff; --card-bg-alt: #f0f0f0;
    --text: #333; --text-heading: #111; --text-muted: #777; --text-secondary: #555;
    --text-tertiary: #444; --border: #ddd; --border-light: #ccc;
    --grid: #e5e5e5; --tooltip-bg: rgba(255,255,255,0.97); --tooltip-border: #ccc;
    --event-gradient-end: #fff; --event-bg-alt: #f8f8f8;
    --status-live-bg: #d4edda; --status-done-bg: #d6eaf8;
    --crosshair: rgba(0,0,0,0.08);
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
         background: var(--bg); color: var(--text); padding: 20px; transition: background 0.3s, color 0.3s; }
  h1 { font-size: 1.4rem; margin-bottom: 4px; color: var(--text-heading); }
  .subtitle { color: var(--text-muted); font-size: 0.85rem; margin-bottom: 20px; }
  .header-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 4px; flex-wrap: wrap; }
  .header-controls { display: flex; align-items: center; gap: 8px; margin-left: auto; }
  .status { display: inline-block; padding: 2px 8px; border-radius: 4px;
            font-size: 0.75rem; font-weight: 600; }
  .status.live { background: var(--status-live-bg); color: #4ade80; animation: pulse 2s ease-in-out infinite; }
  .status.done { background: var(--status-done-bg); color: #60a5fa; }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
  .run-select, .theme-toggle { background: var(--card-bg-alt); color: var(--text);
    border: 1px solid var(--border-light); border-radius: 4px; padding: 4px 8px;
    font-size: 0.8rem; cursor: pointer; }
  .theme-toggle { font-size: 1rem; line-height: 1; padding: 4px 6px; }
  .page-layout { display: grid; grid-template-columns: 1fr 360px; gap: 20px; }
  @media (max-width: 1000px) { .page-layout { grid-template-columns: 1fr; } }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
          gap: 16px; margin-bottom: 20px; }
  .card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; padding: 16px;
          box-shadow: 0 2px 8px rgba(0,0,0,0.1); border-top: 2px solid #4e79a7;
          transition: background 0.3s, border-color 0.3s; }
  .card h2 { font-size: 0.9rem; color: var(--text-secondary); margin-bottom: 12px; text-transform: uppercase;
             letter-spacing: 0.05em; }
  .stats-row { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 16px; }
  .stat { background: var(--card-bg-alt); border-radius: 6px; padding: 12px 16px; min-width: 100px;
          box-shadow: 0 2px 8px rgba(0,0,0,0.1); border-top: 2px solid #4e79a7;
          transition: background 0.3s; }
  .stat .value { font-size: 1.8rem; font-weight: 700; color: var(--text-heading); }
  .stat .label { font-size: 0.75rem; color: var(--text-muted); margin-top: 2px; }
  .outcome-bar { display: flex; align-items: center; margin: 6px 0; }
  .outcome-bar .name { width: 120px; font-size: 0.85rem; color: var(--text-tertiary); }
  .outcome-bar .bar-bg { flex: 1; height: 24px; background: var(--card-bg-alt); border-radius: 6px;
                          overflow: hidden; position: relative; }
  .outcome-bar .bar-fill { height: 100%; border-radius: 6px; transition: width 0.5s ease; }
  .outcome-bar .bar-label { position: absolute; right: 8px; top: 3px; font-size: 0.75rem;
                             color: #fff; font-weight: 600; }
  canvas { max-height: 350px; }
  .field-select { background: var(--card-bg-alt); color: var(--text-tertiary); border: 1px solid var(--border-light);
                  border-radius: 4px; padding: 4px 8px; font-size: 0.8rem; margin-bottom: 8px; }
  .wc-heatmap { width: 100%; border-collapse: collapse; margin-bottom: 12px; }
  .wc-heatmap td, .wc-heatmap th { padding: 2px 4px; font-size: 0.7rem; text-align: center; }
  .wc-heatmap th { color: var(--text-muted); font-weight: 400; }
  .wc-heatmap .wc-cell { width: 22px; height: 22px; border-radius: 3px; cursor: default; }
  .wc-heatmap .wc-hit { background: #edc948; }
  .wc-heatmap .wc-miss { background: var(--card-bg-alt); }
  .wc-heatmap .traj-label { text-align: right; color: var(--text-muted); padding-right: 6px; }
  .wc-tooltip { position: relative; }
  .wc-tooltip:hover::after { content: attr(data-tip); position: absolute; bottom: 120%;
    left: 50%; transform: translateX(-50%); background: var(--border); color: #edc948; padding: 3px 8px;
    border-radius: 4px; font-size: 0.7rem; white-space: nowrap; z-index: 10;
    pointer-events: none; }
  .empty { color: #555; font-style: italic; padding: 40px; text-align: center; }
  .event-log { background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px;
               padding: 16px; height: calc(100vh - 120px); overflow-y: auto;
               position: sticky; top: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);
               border-top: 2px solid #4e79a7; transition: background 0.3s, border-color 0.3s; }
  .event-log h2 { font-size: 0.9rem; color: var(--text-secondary); margin-bottom: 12px;
                   text-transform: uppercase; letter-spacing: 0.05em; }
  .event { margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid var(--card-bg-alt); }
  .event:last-child { border-bottom: none; }
  .event .meta { font-size: 0.7rem; color: #666; margin-bottom: 3px; display: flex;
                 align-items: center; gap: 6px; }
  .event .meta .tag { padding: 1px 6px; border-radius: 3px; font-weight: 600;
                       font-size: 0.65rem; text-transform: uppercase; }
  .tag.narrative { background: #1a2a3a; color: #60a5fa; }
  .tag.proposal { background: #1a3a2a; color: #4ade80; font-size: 0.7rem; font-weight: 700; }
  .tag.wildcard { background: #3a2a1a; color: #edc948; }
  .tag.outcome { background: #2a1a3a; color: #c084fc; }
  .event .text { font-size: 0.8rem; color: var(--text-tertiary); line-height: 1.4;
    max-height: 2.8em; overflow: hidden; cursor: pointer; position: relative; }
  .event .text.expanded { max-height: none; }
  .event .text:not(.expanded)::after { content: '... click to expand'; position: absolute;
    right: 0; bottom: 0; background: linear-gradient(to right, transparent, var(--event-gradient-end) 40%);
    padding-left: 20px; color: #666; font-size: 0.7rem; }
  .event-filter { display: flex; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; }
  .event-filter button { background: var(--card-bg-alt); border: 1px solid var(--border-light); color: var(--text-muted);
                          padding: 3px 10px; border-radius: 4px; cursor: pointer;
                          font-size: 0.7rem; }
  .event-filter button.active { border-color: #555; color: var(--text-heading); }
  .proposal-fields { margin: 4px 0; font-size: 0.75rem; color: var(--text-muted); }
  .proposal-fields code { background: #1a2a1a; padding: 1px 5px; border-radius: 3px;
                           font-size: 0.7rem; color: #4ade80; margin-right: 4px; }
  .proposal-reasoning { margin: 6px 0 0 0; padding: 6px 10px; border-left: 3px solid var(--border-light);
                         font-size: 0.78rem; color: var(--text-secondary); line-height: 1.5;
                         background: var(--event-bg-alt); border-radius: 0 4px 4px 0; }
  .proposal-status { margin-left: auto; font-weight: 600; font-size: 0.75rem; }
  .wc-legend { display: flex; gap: 12px; align-items: center; margin-top: 8px;
               font-size: 0.7rem; color: var(--text-muted); }
  .wc-legend-swatch { display: inline-block; width: 14px; height: 14px; border-radius: 3px;
                       vertical-align: middle; margin-right: 4px; }
  .stat .icon { font-size: 1rem; margin-bottom: 4px; }
  .footer { text-align: center; padding: 16px 0 4px; font-size: 0.7rem; color: #444; }
</style>
</head>
<body>
<div class="header-bar">
  <h1 id="title">minimal-agora dashboard</h1>
  <span class="status live" id="status">connecting...</span>
  <div class="header-controls">
    <select class="run-select" id="run-select" title="Switch simulation run"></select>
    <button class="theme-toggle" id="theme-toggle" title="Toggle light/dark mode">&#9790;</button>
  </div>
</div>
<p class="subtitle" id="subtitle"></p>

<div class="page-layout">
<div class="main-col">
  <div class="stats-row" id="stats"></div>
  <div class="grid">
    <div class="card" id="outcomes-card">
      <h2>Outcome Distribution</h2>
      <div id="outcomes"></div>
    </div>
    <div class="card">
      <h2>Steps to Outcome</h2>
      <canvas id="steps-chart"></canvas>
    </div>
  </div>
  <div class="grid">
    <div class="card" id="timelines-card" style="display:none">
      <h2 id="timelines-title">Field Timelines</h2>
      <select class="field-select" id="timeline-field-select" style="display:none"></select>
      <canvas id="timelines-chart"></canvas>
    </div>
    <div class="card" id="fitness-card" style="display:none">
      <h2>Fitness Tracking</h2>
      <canvas id="fitness-chart"></canvas>
    </div>
  </div>
  <div class="grid" id="pop-grid"></div>
  <div class="grid">
    <div class="card" id="traj-compare-card" style="display:none">
      <h2>Trajectory Comparison</h2>
      <select class="field-select" id="traj-field-select"></select>
      <canvas id="traj-compare-chart"></canvas>
    </div>
    <div class="card" id="agent-activity-card" style="display:none">
      <h2>Agent Activity</h2>
      <canvas id="agent-activity-chart"></canvas>
    </div>
  </div>
  <div class="grid">
    <div class="card" id="wildcard-impact-card" style="display:none">
      <h2>Wildcard Impact</h2>
      <div id="wc-heatmap-container"></div>
      <canvas id="wc-histogram-chart"></canvas>
    </div>
  </div>
</div>
<div class="event-log" id="event-log">
  <h2>Simulation Log</h2>
  <div class="event-filter" id="event-filter">
    <button class="active" data-type="all">All</button>
    <button class="active" data-type="narrative">Narrative</button>
    <button class="active" data-type="wildcard">Wildcards</button>
    <button class="active" data-type="outcome">Outcomes</button>
    <button class="active" data-type="proposal">Proposals</button>
  </div>
  <div id="events"><div class="empty">waiting for events...</div></div>
</div>
</div>
<div class="footer">minimal-agora v0.1 &bull; powered by Chart.js</div>

<script>
const COLORS = ['#4e79a7','#f28e2b','#e15759','#76b7b2','#59a14f',
                '#edc948','#b07aa1','#ff9da7','#9c755f','#bab0ac'];
const charts = {};

function getThemeColors() {
  const cs = getComputedStyle(document.documentElement);
  return {
    grid: cs.getPropertyValue('--grid').trim(),
    text: cs.getPropertyValue('--text').trim(),
    textMuted: cs.getPropertyValue('--text-muted').trim(),
    textSecondary: cs.getPropertyValue('--text-secondary').trim(),
    textTertiary: cs.getPropertyValue('--text-tertiary').trim(),
    textHeading: cs.getPropertyValue('--text-heading').trim(),
    tooltipBg: cs.getPropertyValue('--tooltip-bg').trim(),
    tooltipBorder: cs.getPropertyValue('--tooltip-border').trim(),
    crosshair: cs.getPropertyValue('--crosshair').trim(),
  };
}

function applyChartDefaults() {
  const tc = getThemeColors();
  Chart.defaults.animation.duration = 800;
  Chart.defaults.animation.easing = 'easeOutQuart';
  Chart.defaults.interaction.mode = 'index';
  Chart.defaults.interaction.intersect = false;
  Chart.defaults.plugins.tooltip.backgroundColor = tc.tooltipBg;
  Chart.defaults.plugins.tooltip.borderColor = tc.tooltipBorder;
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.titleColor = tc.textHeading;
  Chart.defaults.plugins.tooltip.bodyColor = tc.textTertiary;
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 6;
}
applyChartDefaults();

Chart.register({
  id: 'crosshair',
  afterDraw(chart) {
    if (chart.tooltip && chart.tooltip._active && chart.tooltip._active.length) {
      const x = chart.tooltip._active[0].element.x;
      const ctx = chart.ctx;
      const top = chart.chartArea.top;
      const bottom = chart.chartArea.bottom;
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(x, top);
      ctx.lineTo(x, bottom);
      ctx.lineWidth = 1;
      ctx.strokeStyle = getThemeColors().crosshair;
      ctx.stroke();
      ctx.restore();
    }
  }
});

function gradientBg(color) {
  return function(context) {
    if (!context.chart.chartArea) return color + '00';
    const {top, bottom} = context.chart.chartArea;
    const ctx = context.chart.ctx;
    const g = ctx.createLinearGradient(0, top, 0, bottom);
    g.addColorStop(0, color + '40');
    g.addColorStop(1, color + '00');
    return g;
  };
}

function lineDataset(label, data, color, fill) {
  return {
    label, data,
    borderColor: color,
    backgroundColor: fill !== false ? gradientBg(color) : color + '22',
    fill: fill !== false,
    tension: 0.3,
    pointRadius: 2,
    pointHoverRadius: 6,
    borderWidth: 2.5,
  };
}

function themedScales(opts) {
  const tc = getThemeColors();
  const result = {};
  for (const [axis, cfg] of Object.entries(opts)) {
    result[axis] = Object.assign({}, cfg, {
      grid: Object.assign({ color: tc.grid }, cfg.grid || {}),
      ticks: Object.assign({ color: axis === 'x' ? tc.textTertiary : tc.textMuted }, cfg.ticks || {}),
    });
    if (cfg.title) result[axis].title = Object.assign({}, cfg.title, { color: tc.textMuted });
  }
  return result;
}

function initChart(id, config) {
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(document.getElementById(id), config);
  return charts[id];
}

function renderStats(data) {
  const el = document.getElementById('stats');
  const n = data.n_trajectories || 0;
  const nOutcomes = Object.keys(data.outcomes || {}).length;
  el.innerHTML = `
    <div class="stat"><div class="icon">&#x1f4ca;</div><div class="value">${n}</div><div class="label">trajectories</div></div>
    <div class="stat"><div class="icon">&#x1f3af;</div><div class="value">${nOutcomes}</div><div class="label">distinct outcomes</div></div>
  `;
}

function renderOutcomes(data) {
  const el = document.getElementById('outcomes');
  const outcomes = data.outcomes || {};
  const n = data.n_trajectories || 1;
  const sorted = Object.entries(outcomes).sort((a,b) => b[1].count - a[1].count);
  if (!sorted.length) { el.innerHTML = '<div class="empty">waiting for trajectories...</div>'; return; }

  el.innerHTML = sorted.map(([name, o], i) => {
    const pct = (o.rate * 100).toFixed(1);
    const color = COLORS[i % COLORS.length];
    return `<div class="outcome-bar">
      <span class="name">${name}</span>
      <div class="bar-bg">
        <div class="bar-fill" style="width:${pct}%;background:${color}"></div>
        <span class="bar-label">${o.count}/${n} (${pct}%)</span>
      </div>
    </div>`;
  }).join('');
}

function renderStepsChart(data) {
  const outcomes = data.outcomes || {};
  const labels = Object.keys(outcomes).sort();
  if (!labels.length) return;
  const tc = getThemeColors();
  const values = labels.map(l => outcomes[l].mean_steps);
  initChart('steps-chart', {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: labels.map((_, i) => COLORS[i % COLORS.length] + '99'),
        borderColor: labels.map((_, i) => COLORS[i % COLORS.length]),
        borderWidth: 1,
        borderRadius: 4
      }]
    },
    options: {
      responsive: true, plugins: { legend: { display: false } },
      scales: themedScales({
        y: { title: { display: true, text: 'mean steps' } },
        x: {}
      })
    },
    plugins: [{
      afterDatasetsDraw(chart) {
        const ctx = chart.ctx;
        chart.getDatasetMeta(0).data.forEach((bar, i) => {
          if (values[i] == null) return;
          ctx.save();
          ctx.fillStyle = tc.textTertiary;
          ctx.font = '11px -apple-system, system-ui, sans-serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'bottom';
          ctx.fillText(values[i].toFixed(1), bar.x, bar.y - 4);
          ctx.restore();
        });
      }
    }]
  });
}

function renderTimelines(data) {
  const tt = data.trajectory_timelines || {};
  const timelines = data.timelines || {};
  const fields = Object.keys(tt);
  if (!fields.length) return;

  document.getElementById('timelines-card').style.display = '';
  const sel = document.getElementById('timeline-field-select');
  if (fields.length > 1) {
    sel.style.display = '';
    const prev = sel.value;
    sel.innerHTML = fields.map(f =>
      `<option value="${f}"${f === prev ? ' selected' : ''}>${f}</option>`
    ).join('');
  } else {
    sel.style.display = 'none';
  }
  const field = sel.value || fields[0];
  document.getElementById('timelines-title').textContent = 'Field Timelines: ' + field;

  const trajData = tt[field] || {};
  const tids = Object.keys(trajData);
  if (!tids.length) return;

  const datasets = [];
  const tc = getThemeColors();

  tids.forEach((tid, i) => {
    const color = COLORS[i % COLORS.length];
    datasets.push({
      label: 'T' + tid + ': ' + field,
      data: trajData[tid].map(p => ({x: p.step, y: p.value})),
      borderColor: color + '99',
      backgroundColor: color + '22',
      fill: false,
      tension: 0.3,
      pointRadius: 1,
      pointHoverRadius: 5,
      borderWidth: 1.5,
    });
  });

  const meanSeries = timelines[field];
  if (meanSeries && meanSeries.length) {
    datasets.push({
      label: 'mean',
      data: meanSeries.map(s => ({x: s.step, y: s.mean})),
      borderColor: '#fff',
      backgroundColor: 'transparent',
      fill: false,
      tension: 0.3,
      pointRadius: 0,
      pointHoverRadius: 4,
      borderWidth: 3,
    });
  }

  const wcEvents = (data.events || []).filter(e => e.type === 'wildcard');
  const wcSteps = {};
  wcEvents.forEach(e => { wcSteps[e.step] = e.name || 'wildcard'; });
  const wcAnnotations = {};
  Object.entries(wcSteps).forEach(([step, name]) => {
    wcAnnotations['wc' + step] = {
      type: 'line', xMin: +step, xMax: +step,
      borderColor: '#edc94866', borderWidth: 1.5, borderDash: [5, 3],
      label: { display: true, content: name, position: 'start',
               color: '#edc948', backgroundColor: 'rgba(20,20,20,0.8)',
               font: { size: 9 }, padding: 2 }
    };
  });
  const hasAnnotations = Object.keys(wcAnnotations).length > 0;

  initChart('timelines-chart', {
    type: 'line',
    data: { datasets },
    options: {
      responsive: true,
      scales: themedScales({
        x: { type: 'linear', title: { display: true, text: 'step' },
             ticks: { callback: function(v) { return 'Step ' + v; } } },
        y: { title: { display: true, text: field } }
      }),
      plugins: {
        legend: { labels: { color: tc.textTertiary } },
        annotation: hasAnnotations ? { annotations: wcAnnotations } : undefined
      }
    }
  });
}

function renderFitness(data) {
  const fitness = data.fitness || [];
  if (!fitness.length) return;
  const tc = getThemeColors();
  document.getElementById('fitness-card').style.display = '';
  initChart('fitness-chart', {
    type: 'line',
    data: {
      datasets: [
        Object.assign(lineDataset('mean', fitness.map(f => ({x: f.step, y: f.mean})), '#59a14f'), {}),
        { label: 'range', data: fitness.map(f => ({x: f.step, y: f.max})),
          borderColor: '#59a14f44', backgroundColor: '#59a14f11',
          fill: { target: '+1', above: '#59a14f11' }, tension: 0.3, pointRadius: 0, borderWidth: 1 },
        { label: '_min', data: fitness.map(f => ({x: f.step, y: f.min})),
          borderColor: '#59a14f44', fill: false, tension: 0.3, pointRadius: 0, borderWidth: 1 }
      ]
    },
    options: {
      responsive: true,
      scales: themedScales({
        x: { type: 'linear', title: { display: true, text: 'step' } },
        y: { title: { display: true, text: 'fitness' } }
      }),
      plugins: { legend: { labels: { color: tc.textTertiary, filter: (item) => !item.text.startsWith('_') } } }
    }
  });
}

function renderPopulations(data) {
  const pops = data.populations || {};
  const popNames = Object.keys(pops);
  if (!popNames.length) return;
  const tc = getThemeColors();
  const grid = document.getElementById('pop-grid');
  const scoreFields = new Set();
  popNames.forEach(p => Object.keys(pops[p]).forEach(s => scoreFields.add(s)));

  scoreFields.forEach(sf => {
    let cardId = `pop-${sf}`;
    let card = document.getElementById(cardId);
    if (!card) {
      card = document.createElement('div');
      card.className = 'card';
      card.id = cardId;
      card.innerHTML = `<h2>Population: ${sf}</h2><canvas id="pop-chart-${sf}"></canvas>`;
      grid.appendChild(card);
    }

    const datasets = popNames.map((pop, i) => {
      const series = pops[pop][sf] || [];
      const color = COLORS[i % COLORS.length];
      return lineDataset(pop, series.map(s => ({x: s.step, y: s.mean})), color);
    });

    initChart(`pop-chart-${sf}`, {
      type: 'line',
      data: { datasets },
      options: {
        responsive: true,
        scales: themedScales({
          x: { type: 'linear', title: { display: true, text: 'step' } },
          y: { title: { display: true, text: sf } }
        }),
        plugins: { legend: { labels: { color: tc.textTertiary } } }
      }
    });
  });
}

function renderTrajectoryComparison(data) {
  const tt = data.trajectory_timelines || {};
  const fields = Object.keys(tt);
  if (!fields.length) return;
  const tc = getThemeColors();
  document.getElementById('traj-compare-card').style.display = '';
  const sel = document.getElementById('traj-field-select');
  const prev = sel.value;
  sel.innerHTML = fields.map(f => `<option value="${f}"${f === prev ? ' selected' : ''}>${f}</option>`).join('');
  const field = sel.value || fields[0];
  const trajData = tt[field] || {};
  const tids = Object.keys(trajData);
  if (!tids.length) return;

  const datasets = tids.map((tid, i) => {
    const color = COLORS[i % COLORS.length];
    return lineDataset('T' + tid, trajData[tid].map(p => ({x: p.step, y: p.value})), color);
  });

  initChart('traj-compare-chart', {
    type: 'line',
    data: { datasets },
    options: {
      responsive: true,
      scales: themedScales({
        x: { type: 'linear', title: { display: true, text: 'step' } },
        y: { title: { display: true, text: field } }
      }),
      plugins: { legend: { labels: { color: tc.textTertiary } } }
    }
  });
}

function renderWildcardImpact(data) {
  const events = (data.events || []).filter(e => e.type === 'wildcard');
  if (!events.length) return;

  document.getElementById('wildcard-impact-card').style.display = '';

  const tids = [...new Set(events.map(e => e.trajectory))].sort((a,b) => a - b);
  const maxStep = Math.max(...events.map(e => e.step));
  const steps = Array.from({length: maxStep + 1}, (_, i) => i);

  const wcMap = {};
  events.forEach(e => { wcMap[e.trajectory + '-' + e.step] = e.name || e.text.split(':')[0]; });

  const headerCells = steps.map(s => `<th>${s}</th>`).join('');
  const rows = tids.map(tid => {
    const cells = steps.map(s => {
      const key = tid + '-' + s;
      const name = wcMap[key];
      if (name) return `<td><div class="wc-cell wc-hit wc-tooltip" data-tip="${escapeHtml(name)}"></div></td>`;
      return `<td><div class="wc-cell wc-miss"></div></td>`;
    }).join('');
    return `<tr><td class="traj-label">T${tid}</td>${cells}</tr>`;
  }).join('');

  document.getElementById('wc-heatmap-container').innerHTML =
    `<div style="overflow-x:auto"><table class="wc-heatmap"><tr><th></th>${headerCells}</tr>${rows}</table></div>` +
    `<div class="wc-legend"><span><span class="wc-legend-swatch" style="background:#edc948"></span>Wildcard fired</span>` +
    `<span><span class="wc-legend-swatch" style="background:var(--card-bg-alt);border:1px solid var(--border-light)"></span>No wildcard</span></div>`;

  const freq = new Array(maxStep + 1).fill(0);
  events.forEach(e => { freq[e.step] = (freq[e.step] || 0) + 1; });

  initChart('wc-histogram-chart', {
    type: 'bar',
    data: {
      labels: steps.map(s => 'Step ' + s),
      datasets: [{
        label: 'Wildcards fired',
        data: freq,
        backgroundColor: '#edc94899',
        borderColor: '#edc948',
        borderRadius: 4,
        borderWidth: 1
      }]
    },
    options: {
      responsive: true,
      scales: themedScales({
        y: { title: { display: true, text: 'count' }, ticks: { stepSize: 1 } },
        x: {}
      }),
      plugins: { legend: { display: false } }
    }
  });
}

function renderAgentActivity(data) {
  const proposals = (data.events || []).filter(e => e.type === 'proposal');
  if (!proposals.length) return;
  const tc = getThemeColors();
  document.getElementById('agent-activity-card').style.display = '';

  const agentStats = {};
  proposals.forEach(e => {
    if (!agentStats[e.agent]) agentStats[e.agent] = { total: 0, accepted: 0 };
    agentStats[e.agent].total++;
    if (e.accepted) agentStats[e.agent].accepted++;
  });

  const agents = Object.keys(agentStats).sort();
  const totals = agents.map(a => agentStats[a].total);
  const accepted = agents.map(a => agentStats[a].accepted);
  const rates = agents.map(a => {
    const s = agentStats[a];
    return s.total ? Math.round(s.accepted / s.total * 100) : 0;
  });

  initChart('agent-activity-chart', {
    type: 'bar',
    data: {
      labels: agents,
      datasets: [
        { label: 'Total proposals', data: totals,
          backgroundColor: COLORS[0] + '99', borderColor: COLORS[0], borderWidth: 1, borderRadius: 4 },
        { label: 'Accepted', data: accepted,
          backgroundColor: COLORS[4] + '99', borderColor: COLORS[4], borderWidth: 1, borderRadius: 4 }
      ]
    },
    options: {
      indexAxis: 'y', responsive: true,
      scales: themedScales({
        x: { title: { display: true, text: 'count' }, ticks: { stepSize: 1 } },
        y: {}
      }),
      plugins: { legend: { labels: { color: tc.textTertiary } } }
    },
    plugins: [{
      afterDatasetsDraw(chart) {
        const meta = chart.getDatasetMeta(1);
        const ctx = chart.ctx;
        meta.data.forEach((bar, i) => {
          ctx.save();
          ctx.fillStyle = tc.textSecondary;
          ctx.font = '11px -apple-system, system-ui, sans-serif';
          ctx.textAlign = 'left';
          ctx.textBaseline = 'middle';
          ctx.fillText(rates[i] + '%', bar.x + 6, bar.y);
          ctx.restore();
        });
      }
    }]
  });
}

let activeFilters = new Set(['narrative', 'wildcard', 'outcome', 'proposal']);
let allEvents = [];

function renderEvents(data) {
  allEvents = data.events || [];
  const el = document.getElementById('events');
  const filtered = allEvents.filter(e => activeFilters.has(e.type));

  if (!filtered.length) {
    el.innerHTML = '<div class="empty">waiting for events...</div>';
    return;
  }

  const grouped = {};
  filtered.forEach(e => {
    const key = `t${e.trajectory}-s${e.step}`;
    if (!grouped[key]) grouped[key] = { trajectory: e.trajectory, step: e.step, items: [] };
    grouped[key].items.push(e);
  });

  el.innerHTML = Object.values(grouped).map(g => {
    return g.items.map(e => {
      if (e.type === 'proposal') {
        const status = e.accepted
          ? '<span class="proposal-status" style="color:#4ade80">&#x2713; accepted</span>'
          : '<span class="proposal-status" style="color:#f87171">&#x2717; rejected</span>';
        const fields = (e.proposed_fields || []).map(f =>
          '<code>' + escapeHtml(f) + '</code>').join(' ');
        return `<div class="event">
          <div class="meta">
            <span class="tag proposal">${escapeHtml(e.agent)}</span>
            <span>T${e.trajectory} Step ${e.step}</span>
            ${status}
          </div>
          ${fields ? '<div class="proposal-fields">Proposed: ' + fields + '</div>' : ''}
          <div class="proposal-reasoning"><strong>${escapeHtml(e.agent)}</strong>: ${escapeHtml(e.text)}</div>
        </div>`;
      }
      return `<div class="event">
        <div class="meta">
          <span class="tag ${e.type}">${e.type}</span>
          <span>T${e.trajectory} Step ${e.step}</span>
        </div>
        <div class="text">${escapeHtml(e.text)}</div>
      </div>`;
    }).join('');
  }).join('');

  el.scrollTop = el.scrollHeight;
}

function escapeHtml(s) {
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

document.getElementById('event-filter').addEventListener('click', (e) => {
  if (e.target.tagName !== 'BUTTON') return;
  const type = e.target.dataset.type;
  if (type === 'all') {
    const allActive = ['narrative','wildcard','outcome','proposal'].every(t => activeFilters.has(t));
    if (allActive) { activeFilters.clear(); }
    else { activeFilters = new Set(['narrative','wildcard','outcome','proposal']); }
  } else {
    activeFilters.has(type) ? activeFilters.delete(type) : activeFilters.add(type);
  }
  document.querySelectorAll('#event-filter button').forEach(b => {
    if (b.dataset.type === 'all') {
      b.classList.toggle('active', activeFilters.size === 4);
    } else {
      b.classList.toggle('active', activeFilters.has(b.dataset.type));
    }
  });
  renderEvents({ events: allEvents });
});

document.getElementById('events').addEventListener('click', (e) => {
  const textEl = e.target.closest('.event .text');
  if (textEl) textEl.classList.toggle('expanded');
});

let lastData = {};
let currentRunDir = null;
let evtSource = null;

function render(data) {
  lastData = data;
  document.getElementById('title').textContent = data.scenario || 'minimal-agora dashboard';
  document.getElementById('subtitle').textContent =
    `${data.n_trajectories || 0} trajectories` + (data.run_dir ? ` \\u2014 ${data.run_dir}` : '');
  renderStats(data);
  renderOutcomes(data);
  renderStepsChart(data);
  renderTimelines(data);
  renderFitness(data);
  renderPopulations(data);
  renderTrajectoryComparison(data);
  renderWildcardImpact(data);
  renderAgentActivity(data);
  renderEvents(data);
}

function reRenderAll() {
  applyChartDefaults();
  if (lastData && lastData.n_trajectories) render(lastData);
}

// Theme toggle
function setTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  document.getElementById('theme-toggle').textContent = theme === 'dark' ? '\\u263e' : '\\u2600';
  try { localStorage.setItem('agora-theme', theme); } catch(e) {}
  reRenderAll();
}
(function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem('agora-theme'); } catch(e) {}
  setTheme(saved || 'dark');
})();
document.getElementById('theme-toggle').addEventListener('click', () => {
  const current = document.documentElement.getAttribute('data-theme');
  setTheme(current === 'dark' ? 'light' : 'dark');
});

// Timeline field selector
document.getElementById('timeline-field-select').addEventListener('change', () => {
  if (lastData.trajectory_timelines) renderTimelines(lastData);
});

document.getElementById('traj-field-select').addEventListener('change', () => {
  if (lastData.trajectory_timelines) renderTrajectoryComparison(lastData);
});

// Simulation switcher
function loadRuns() {
  fetch('/api/runs').then(r => r.json()).then(runs => {
    const sel = document.getElementById('run-select');
    sel.innerHTML = runs.map(r =>
      `<option value="${r.dirname}"${r.current ? ' selected' : ''}>${r.scenario} (${r.n_trajectories} traj)</option>`
    ).join('');
    const current = runs.find(r => r.current);
    if (current) currentRunDir = current.dirname;
  }).catch(() => {});
}
loadRuns();

document.getElementById('run-select').addEventListener('change', (e) => {
  const dirname = e.target.value;
  currentRunDir = dirname;
  if (evtSource) { evtSource.close(); evtSource = null; }
  document.getElementById('status').textContent = 'loading...';
  document.getElementById('status').className = 'status done';
  fetch('/api/data?run=' + encodeURIComponent(dirname))
    .then(r => r.json())
    .then(render)
    .catch(() => {});
});

// Connect via SSE for live updates
function connectSSE() {
  evtSource = new EventSource('/api/stream');
  evtSource.onmessage = (e) => {
    const data = JSON.parse(e.data);
    document.getElementById('status').textContent = 'live';
    document.getElementById('status').className = 'status live';
    render(data);
  };
  evtSource.onerror = () => {
    document.getElementById('status').textContent = 'disconnected';
    document.getElementById('status').className = 'status done';
  };
}
connectSSE();

// Also fetch once immediately
fetch('/api/data').then(r => r.json()).then(render).catch(() => {});
</script>
</body>
</html>"""


def start_dashboard(
    run_dir: Path,
    port: int = 8765,
    fields: list[str] | None = None,
    populations: list[str] | None = None,
    score_fields: list[str] | None = None,
) -> None:
    class ConfiguredHandler(DashboardHandler):
        pass

    ConfiguredHandler.run_dir = run_dir
    ConfiguredHandler.runs_root = run_dir.parent
    ConfiguredHandler.fields = fields or []
    ConfiguredHandler.populations = populations or []
    ConfiguredHandler.score_fields = score_fields or []

    server = HTTPServer(("127.0.0.1", port), ConfiguredHandler)
    print(f"Dashboard: http://127.0.0.1:{port}")
    print(f"Watching: {run_dir}")
    print("Press Ctrl+C to stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
        server.server_close()
