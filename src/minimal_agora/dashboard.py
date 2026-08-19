from __future__ import annotations

import json
import time
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from minimal_agora.analysis import (
    _get_nested,
    compute_statistics,
    extract_field_timelines,
    load_trajectories,
)


class DashboardHandler(SimpleHTTPRequestHandler):
    run_dir: Path
    fields: list[str]
    populations: list[str]
    score_fields: list[str]

    def do_GET(self):
        if self.path == "/":
            self._serve_html()
        elif self.path == "/api/data":
            self._serve_data()
        elif self.path == "/api/stream":
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

    def _serve_data(self):
        data = _collect_data(self.run_dir, self.fields, self.populations, self.score_fields)
        body = json.dumps(data).encode()
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

    pop_data = {}
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
            vals = [h[i] for h in all_fitness if i < len(h) and h[i] is not None]
            if vals:
                fitness_data.append({"step": i, "mean": _mean(vals), "min": min(vals), "max": max(vals)})

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
                        "text": p.reasoning[:200],
                        "accepted": accepted,
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
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>minimal-agora dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
         background: #0a0a0a; color: #e0e0e0; padding: 20px; }
  h1 { font-size: 1.4rem; margin-bottom: 4px; color: #fff; }
  .subtitle { color: #888; font-size: 0.85rem; margin-bottom: 20px; }
  .status { display: inline-block; padding: 2px 8px; border-radius: 4px;
            font-size: 0.75rem; font-weight: 600; }
  .status.live { background: #1a3a1a; color: #4ade80; }
  .status.done { background: #1a2a3a; color: #60a5fa; }
  .page-layout { display: grid; grid-template-columns: 1fr 360px; gap: 20px; }
  @media (max-width: 1000px) { .page-layout { grid-template-columns: 1fr; } }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
          gap: 16px; margin-bottom: 20px; }
  .card { background: #141414; border: 1px solid #222; border-radius: 8px; padding: 16px; }
  .card h2 { font-size: 0.9rem; color: #aaa; margin-bottom: 12px; text-transform: uppercase;
             letter-spacing: 0.05em; }
  .stats-row { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 16px; }
  .stat { background: #1a1a1a; border-radius: 6px; padding: 12px 16px; min-width: 100px; }
  .stat .value { font-size: 1.8rem; font-weight: 700; color: #fff; }
  .stat .label { font-size: 0.75rem; color: #888; margin-top: 2px; }
  .outcome-bar { display: flex; align-items: center; margin: 6px 0; }
  .outcome-bar .name { width: 120px; font-size: 0.85rem; color: #ccc; }
  .outcome-bar .bar-bg { flex: 1; height: 24px; background: #1a1a1a; border-radius: 4px;
                          overflow: hidden; position: relative; }
  .outcome-bar .bar-fill { height: 100%; border-radius: 4px; transition: width 0.5s ease; }
  .outcome-bar .bar-label { position: absolute; right: 8px; top: 3px; font-size: 0.75rem;
                             color: #fff; font-weight: 600; }
  canvas { max-height: 300px; }
  .field-select { background: #1a1a1a; color: #ccc; border: 1px solid #333; border-radius: 4px;
                  padding: 4px 8px; font-size: 0.8rem; margin-bottom: 8px; }
  .wc-heatmap { width: 100%; border-collapse: collapse; margin-bottom: 12px; }
  .wc-heatmap td, .wc-heatmap th { padding: 2px 4px; font-size: 0.7rem; text-align: center; }
  .wc-heatmap th { color: #888; font-weight: 400; }
  .wc-heatmap .wc-cell { width: 18px; height: 18px; border-radius: 3px; cursor: default; }
  .wc-heatmap .wc-hit { background: #fbbf24; }
  .wc-heatmap .wc-miss { background: #1a1a1a; }
  .wc-heatmap .traj-label { text-align: right; color: #888; padding-right: 6px; }
  .wc-tooltip { position: relative; }
  .wc-tooltip:hover::after { content: attr(data-tip); position: absolute; bottom: 120%;
    left: 50%; transform: translateX(-50%); background: #222; color: #fbbf24; padding: 3px 8px;
    border-radius: 4px; font-size: 0.7rem; white-space: nowrap; z-index: 10;
    pointer-events: none; }
  .empty { color: #555; font-style: italic; padding: 40px; text-align: center; }
  .event-log { background: #141414; border: 1px solid #222; border-radius: 8px;
               padding: 16px; height: calc(100vh - 120px); overflow-y: auto;
               position: sticky; top: 20px; }
  .event-log h2 { font-size: 0.9rem; color: #aaa; margin-bottom: 12px;
                   text-transform: uppercase; letter-spacing: 0.05em; }
  .event { margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #1a1a1a; }
  .event:last-child { border-bottom: none; }
  .event .meta { font-size: 0.7rem; color: #666; margin-bottom: 3px; display: flex;
                 align-items: center; gap: 6px; }
  .event .meta .tag { padding: 1px 6px; border-radius: 3px; font-weight: 600;
                       font-size: 0.65rem; text-transform: uppercase; }
  .tag.narrative { background: #1a2a3a; color: #60a5fa; }
  .tag.proposal { background: #1a3a2a; color: #4ade80; }
  .tag.wildcard { background: #3a2a1a; color: #fbbf24; }
  .tag.outcome { background: #2a1a3a; color: #c084fc; }
  .event .text { font-size: 0.8rem; color: #ccc; line-height: 1.4; }
  .event-filter { display: flex; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; }
  .event-filter button { background: #1a1a1a; border: 1px solid #333; color: #888;
                          padding: 3px 10px; border-radius: 4px; cursor: pointer;
                          font-size: 0.7rem; }
  .event-filter button.active { border-color: #555; color: #fff; }
  .colors { --c0: #2196F3; --c1: #F44336; --c2: #4CAF50; --c3: #FF9800; --c4: #9C27B0;
            --c5: #00BCD4; --c6: #795548; --c7: #607D8B; }
</style>
</head>
<body class="colors">
<div style="display:flex; align-items:center; gap:12px; margin-bottom:4px;">
  <h1 id="title">minimal-agora dashboard</h1>
  <span class="status live" id="status">connecting...</span>
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
      <h2>Field Timelines</h2>
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
    <button data-type="proposal">Proposals</button>
  </div>
  <div id="events"><div class="empty">waiting for events...</div></div>
</div>
</div>

<script>
const COLORS = ['#2196F3','#F44336','#4CAF50','#FF9800','#9C27B0',
                '#00BCD4','#795548','#607D8B','#E91E63','#3F51B5'];
const charts = {};

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
    <div class="stat"><div class="value">${n}</div><div class="label">trajectories</div></div>
    <div class="stat"><div class="value">${nOutcomes}</div><div class="label">distinct outcomes</div></div>
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

  initChart('steps-chart', {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: labels.map(l => outcomes[l].mean_steps),
        backgroundColor: labels.map((_, i) => COLORS[i % COLORS.length] + '99'),
        borderColor: labels.map((_, i) => COLORS[i % COLORS.length]),
        borderWidth: 1
      }]
    },
    options: {
      responsive: true, plugins: { legend: { display: false } },
      scales: { y: { title: { display: true, text: 'mean steps', color: '#888' },
                      grid: { color: '#222' }, ticks: { color: '#888' } },
                x: { grid: { color: '#222' }, ticks: { color: '#ccc' } } }
    }
  });
}

function renderTimelines(data) {
  const timelines = data.timelines || {};
  const fields = Object.keys(timelines);
  if (!fields.length) return;

  document.getElementById('timelines-card').style.display = '';
  const datasets = fields.map((f, i) => {
    const series = timelines[f];
    return {
      label: f,
      data: series.map(s => ({ x: s.step, y: s.mean })),
      borderColor: COLORS[i % COLORS.length],
      backgroundColor: COLORS[i % COLORS.length] + '22',
      fill: false, tension: 0.3, pointRadius: 3
    };
  });

  initChart('timelines-chart', {
    type: 'line',
    data: { datasets },
    options: {
      responsive: true,
      scales: { x: { type: 'linear', title: { display: true, text: 'step', color: '#888' },
                      grid: { color: '#222' }, ticks: { color: '#888' } },
                y: { grid: { color: '#222' }, ticks: { color: '#888' } } },
      plugins: { legend: { labels: { color: '#ccc' } } }
    }
  });
}

function renderFitness(data) {
  const fitness = data.fitness || [];
  if (!fitness.length) return;

  document.getElementById('fitness-card').style.display = '';
  initChart('fitness-chart', {
    type: 'line',
    data: {
      datasets: [
        { label: 'mean', data: fitness.map(f => ({x: f.step, y: f.mean})),
          borderColor: '#4CAF50', fill: false, tension: 0.3 },
        { label: 'range', data: fitness.map(f => ({x: f.step, y: f.max})),
          borderColor: '#4CAF5044', backgroundColor: '#4CAF5011',
          fill: { target: '+1', above: '#4CAF5011' }, tension: 0.3, pointRadius: 0 },
        { label: '_min', data: fitness.map(f => ({x: f.step, y: f.min})),
          borderColor: '#4CAF5044', fill: false, tension: 0.3, pointRadius: 0 }
      ]
    },
    options: {
      responsive: true,
      scales: { x: { type: 'linear', title: { display: true, text: 'step', color: '#888' },
                      grid: { color: '#222' }, ticks: { color: '#888' } },
                y: { title: { display: true, text: 'fitness', color: '#888' },
                     grid: { color: '#222' }, ticks: { color: '#888' } } },
      plugins: { legend: { labels: { color: '#ccc', filter: (item) => !item.text.startsWith('_') } } }
    }
  });
}

function renderPopulations(data) {
  const pops = data.populations || {};
  const popNames = Object.keys(pops);
  if (!popNames.length) return;

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
      return {
        label: pop,
        data: series.map(s => ({x: s.step, y: s.mean})),
        borderColor: COLORS[i % COLORS.length],
        fill: false, tension: 0.3, pointRadius: 3
      };
    });

    initChart(`pop-chart-${sf}`, {
      type: 'line',
      data: { datasets },
      options: {
        responsive: true,
        scales: { x: { type: 'linear', title: { display: true, text: 'step', color: '#888' },
                        grid: { color: '#222' }, ticks: { color: '#888' } },
                  y: { title: { display: true, text: sf, color: '#888' },
                       grid: { color: '#222' }, ticks: { color: '#888' } } },
        plugins: { legend: { labels: { color: '#ccc' } } }
      }
    });
  });
}

function renderTrajectoryComparison(data) {
  const tt = data.trajectory_timelines || {};
  const fields = Object.keys(tt);
  if (!fields.length) return;

  document.getElementById('traj-compare-card').style.display = '';
  const sel = document.getElementById('traj-field-select');
  const prev = sel.value;
  sel.innerHTML = fields.map(f => `<option value="${f}"${f === prev ? ' selected' : ''}>${f}</option>`).join('');
  const field = sel.value || fields[0];
  const trajData = tt[field] || {};
  const tids = Object.keys(trajData);
  if (!tids.length) return;

  const datasets = tids.map((tid, i) => ({
    label: 'T' + tid,
    data: trajData[tid].map(p => ({ x: p.step, y: p.value })),
    borderColor: COLORS[i % COLORS.length],
    fill: false, tension: 0.3, pointRadius: 2, borderWidth: 2
  }));

  initChart('traj-compare-chart', {
    type: 'line',
    data: { datasets },
    options: {
      responsive: true,
      scales: { x: { type: 'linear', title: { display: true, text: 'step', color: '#888' },
                      grid: { color: '#222' }, ticks: { color: '#888' } },
                y: { title: { display: true, text: field, color: '#888' },
                     grid: { color: '#222' }, ticks: { color: '#888' } } },
      plugins: { legend: { labels: { color: '#ccc' } } }
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
    `<div style="overflow-x:auto"><table class="wc-heatmap"><tr><th></th>${headerCells}</tr>${rows}</table></div>`;

  const freq = new Array(maxStep + 1).fill(0);
  events.forEach(e => { freq[e.step] = (freq[e.step] || 0) + 1; });

  initChart('wc-histogram-chart', {
    type: 'bar',
    data: {
      labels: steps.map(s => 'Step ' + s),
      datasets: [{
        label: 'Wildcards fired',
        data: freq,
        backgroundColor: '#fbbf2499',
        borderColor: '#fbbf24',
        borderWidth: 1
      }]
    },
    options: {
      responsive: true,
      scales: { y: { title: { display: true, text: 'count', color: '#888' },
                      grid: { color: '#222' }, ticks: { color: '#888', stepSize: 1 } },
                x: { grid: { color: '#222' }, ticks: { color: '#888' } } },
      plugins: { legend: { display: false } }
    }
  });
}

function renderAgentActivity(data) {
  const proposals = (data.events || []).filter(e => e.type === 'proposal');
  if (!proposals.length) return;

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

  initChart('agent-activity-chart', {
    type: 'bar',
    data: {
      labels: agents,
      datasets: [
        { label: 'Total proposals', data: totals,
          backgroundColor: '#2196F399', borderColor: '#2196F3', borderWidth: 1 },
        { label: 'Accepted', data: accepted,
          backgroundColor: '#4CAF5099', borderColor: '#4CAF50', borderWidth: 1 }
      ]
    },
    options: {
      indexAxis: 'y', responsive: true,
      scales: { x: { title: { display: true, text: 'count', color: '#888' },
                      grid: { color: '#222' }, ticks: { color: '#888', stepSize: 1 } },
                y: { grid: { color: '#222' }, ticks: { color: '#ccc' } } },
      plugins: { legend: { labels: { color: '#ccc' } } }
    }
  });
}

let activeFilters = new Set(['narrative', 'wildcard', 'outcome']);
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
    const items = g.items.map(e => {
      const agent = e.agent ? ` (${e.agent})` : '';
      return `<div class="event">
        <div class="meta">
          <span class="tag ${e.type}">${e.type}</span>
          <span>T${e.trajectory} Step ${e.step}${agent}</span>
        </div>
        <div class="text">${escapeHtml(e.text)}</div>
      </div>`;
    }).join('');
    return items;
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

let lastData = {};

function render(data) {
  lastData = data;
  document.getElementById('title').textContent = data.scenario || 'minimal-agora dashboard';
  document.getElementById('subtitle').textContent = `${data.n_trajectories || 0} trajectories`;
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

document.getElementById('traj-field-select').addEventListener('change', () => {
  if (lastData.trajectory_timelines) renderTrajectoryComparison(lastData);
});

// Connect via SSE for live updates
const evtSource = new EventSource('/api/stream');
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
    handler = partial(DashboardHandler)
    handler.run_dir = run_dir
    handler.fields = fields or []
    handler.populations = populations or []
    handler.score_fields = score_fields or []

    server = HTTPServer(("127.0.0.1", port), handler)
    print(f"Dashboard: http://127.0.0.1:{port}")
    print(f"Watching: {run_dir}")
    print("Press Ctrl+C to stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
        server.server_close()
