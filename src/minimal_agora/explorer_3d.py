"""Three.js 3D state-space explorer for minimal-agora simulation runs.

Generates a self-contained HTML file that visualizes trajectory paths
through state space with interactive axis selection, time scrubbing,
wildcard markers, and orbit controls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from minimal_agora.analysis import load_trajectories
from minimal_agora.models import Trajectory


def _flatten_state(state: dict, prefix: str = "") -> dict[str, float]:
    """Recursively flatten nested dicts, keeping only numeric values."""
    result: dict[str, float] = {}
    for key, value in state.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(_flatten_state(value, full_key))
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            result[full_key] = float(value)
    return result


def _extract_wildcards(run_dir: Path, trajectories: list[Trajectory]) -> list[dict[str, Any]]:
    """Extract wildcard events from board directories."""
    wildcards: list[dict[str, Any]] = []
    for traj in trajectories:
        traj_dir = run_dir / f"trajectory_{traj.trajectory_id:03d}"
        board_dir = traj_dir / "board"
        if not board_dir.exists():
            continue
        for wc_file in sorted(board_dir.glob("wildcard_step_*.json")):
            stem = wc_file.stem  # e.g. wildcard_step_025
            try:
                step_num = int(stem.split("_")[-1])
            except (ValueError, IndexError):
                continue
            try:
                with open(wc_file) as f:
                    wc_data = json.load(f)
                wildcards.append({
                    "trajectory": traj.trajectory_id,
                    "step": step_num,
                    "name": wc_data.get("name", "unknown"),
                })
            except (json.JSONDecodeError, OSError):
                continue
    return wildcards


def extract_state_vectors(run_dir: Path) -> dict[str, Any]:
    """Extract state vectors from all trajectories in a run directory.

    Returns a dict with:
        fields: list of numeric field names found across all trajectories
        trajectories: list of trajectory dicts with id, outcome, and per-step values
        wildcards: list of wildcard event dicts with trajectory, step, and name
    """
    run_dir = Path(run_dir)
    trajectories = load_trajectories(run_dir)

    if not trajectories:
        return {"fields": [], "trajectories": [], "wildcards": []}

    # Collect all numeric fields across all steps of all trajectories
    all_fields: set[str] = set()
    traj_data: list[dict[str, Any]] = []

    for traj in trajectories:
        outcome = "unclassified"
        if traj.outcome:
            outcome = traj.outcome.classification

        steps_data: list[dict[str, Any]] = []
        for step in traj.steps:
            flat = _flatten_state(step.state_after)
            all_fields.update(flat.keys())
            steps_data.append({
                "step": step.step_number,
                "values": flat,
            })

        traj_data.append({
            "id": traj.trajectory_id,
            "outcome": outcome,
            "steps": steps_data,
        })

    wildcards = _extract_wildcards(run_dir, trajectories)

    return {
        "fields": sorted(all_fields),
        "trajectories": traj_data,
        "wildcards": wildcards,
    }


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>State-Space Explorer</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: #0d1117;
    color: #c9d1d9;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    overflow: hidden;
    height: 100vh;
    width: 100vw;
  }
  #controls {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 10;
    background: rgba(13, 17, 23, 0.92);
    backdrop-filter: blur(8px);
    border-bottom: 1px solid #30363d;
    padding: 12px 20px;
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
  }
  #controls label {
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #8b949e;
  }
  #controls select, #controls input[type=range] {
    background: #161b22;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 13px;
    outline: none;
  }
  #controls select:hover, #controls input[type=range]:hover {
    border-color: #58a6ff;
  }
  .axis-group {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .axis-label {
    display: inline-block;
    width: 16px;
    height: 16px;
    border-radius: 3px;
    text-align: center;
    line-height: 16px;
    font-size: 11px;
    font-weight: 700;
    color: #0d1117;
  }
  .axis-x { background: #f47067; }
  .axis-y { background: #57ab5a; }
  .axis-z { background: #6cb6ff; }
  #time-group {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    min-width: 200px;
  }
  #time-slider {
    flex: 1;
    min-width: 100px;
    accent-color: #58a6ff;
  }
  #play-btn {
    background: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 4px;
    padding: 4px 10px;
    cursor: pointer;
    font-size: 14px;
  }
  #play-btn:hover { background: #30363d; }
  #step-display {
    font-size: 13px;
    font-variant-numeric: tabular-nums;
    min-width: 70px;
    text-align: right;
    color: #8b949e;
  }
  #legend {
    position: fixed;
    bottom: 16px;
    left: 16px;
    z-index: 10;
    background: rgba(13, 17, 23, 0.88);
    backdrop-filter: blur(8px);
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 10px 14px;
    font-size: 12px;
    max-height: 260px;
    overflow-y: auto;
  }
  #legend h3 {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #8b949e;
    margin-bottom: 8px;
  }
  .legend-item {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 4px;
  }
  .legend-swatch {
    width: 12px;
    height: 12px;
    border-radius: 2px;
    flex-shrink: 0;
  }
  #tooltip {
    position: fixed;
    z-index: 20;
    background: rgba(22, 27, 34, 0.95);
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 12px;
    pointer-events: none;
    display: none;
    max-width: 300px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
  }
  #tooltip .tt-title {
    font-weight: 600;
    color: #58a6ff;
    margin-bottom: 4px;
  }
  #tooltip .tt-row {
    color: #8b949e;
    white-space: nowrap;
  }
  #tooltip .tt-row span {
    color: #c9d1d9;
  }
  canvas { display: block; }
</style>
</head>
<body>

<div id="controls">
  <div class="axis-group">
    <span class="axis-label axis-x">X</span>
    <select id="sel-x"></select>
  </div>
  <div class="axis-group">
    <span class="axis-label axis-y">Y</span>
    <select id="sel-y"></select>
  </div>
  <div class="axis-group">
    <span class="axis-label axis-z">Z</span>
    <select id="sel-z"></select>
  </div>
  <div id="time-group">
    <label>Step</label>
    <input type="range" id="time-slider" min="0" max="1" value="1" step="1">
    <button id="play-btn">&#9654;</button>
    <span id="step-display">0 / 0</span>
  </div>
</div>

<div id="legend"><h3>Trajectories</h3></div>
<div id="tooltip">
  <div class="tt-title"></div>
  <div class="tt-body"></div>
</div>

<script type="importmap">
{
  "imports": {
    "three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
    "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"
  }
}
</script>

<script type="module">
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

/* ---------- DATA ---------- */
const DATA = __DATA_PLACEHOLDER__;

const fields = DATA.fields;
const trajectories = DATA.trajectories;
const wildcardEvents = DATA.wildcards;

/* ---------- COLOR PALETTE ---------- */
const PALETTE = [
  '#58a6ff', '#f47067', '#57ab5a', '#d2a8ff', '#e3b341',
  '#f78166', '#a5d6ff', '#7ee787', '#d8b4fe', '#ffd33d',
  '#ff9bce', '#79c0ff', '#56d364', '#bc8cff', '#e6edf3',
];

function buildColorMap() {
  const outcomes = [...new Set(trajectories.map(t => t.outcome))];
  const allSame = outcomes.length <= 1;
  const map = {};
  if (allSame) {
    trajectories.forEach((t, i) => {
      map[t.id] = PALETTE[i % PALETTE.length];
    });
  } else {
    outcomes.forEach((o, i) => {
      map[o] = PALETTE[i % PALETTE.length];
    });
  }
  return { map, byOutcome: !allSame };
}

const colorInfo = buildColorMap();

function trajColor(traj) {
  if (colorInfo.byOutcome) return colorInfo.map[traj.outcome] || '#8b949e';
  return colorInfo.map[traj.id] || '#8b949e';
}

/* ---------- LEGEND ---------- */
function buildLegend() {
  const el = document.getElementById('legend');
  let html = '<h3>Trajectories</h3>';
  if (colorInfo.byOutcome) {
    for (const [name, color] of Object.entries(colorInfo.map)) {
      html += `<div class="legend-item"><span class="legend-swatch" style="background:${color}"></span>${name}</div>`;
    }
  } else {
    trajectories.forEach(t => {
      const c = trajColor(t);
      html += `<div class="legend-item"><span class="legend-swatch" style="background:${c}"></span>T${t.id} (${t.outcome})</div>`;
    });
  }
  el.innerHTML = html;
}
buildLegend();

/* ---------- SCENE SETUP ---------- */
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0d1117);
scene.fog = new THREE.FogExp2(0x0d1117, 0.015);

const camera = new THREE.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 0.1, 1000);
camera.position.set(12, 10, 12);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);
document.body.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.minDistance = 2;
controls.maxDistance = 100;

/* Lighting */
scene.add(new THREE.AmbientLight(0x404040, 2));
const dl = new THREE.DirectionalLight(0xffffff, 1.2);
dl.position.set(10, 15, 10);
scene.add(dl);

/* Grid */
const grid = new THREE.GridHelper(20, 20, 0x21262d, 0x21262d);
scene.add(grid);

/* ---------- AXIS LABELS (sprites) ---------- */
function makeTextSprite(text, color) {
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  canvas.width = 128;
  canvas.height = 48;
  ctx.fillStyle = color;
  ctx.font = 'bold 28px sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, 64, 24);
  const tex = new THREE.CanvasTexture(canvas);
  const mat = new THREE.SpriteMaterial({ map: tex, depthTest: false });
  const sprite = new THREE.Sprite(mat);
  sprite.scale.set(2, 0.75, 1);
  return sprite;
}

const axisLabelX = makeTextSprite('X', '#f47067');
const axisLabelY = makeTextSprite('Y', '#57ab5a');
const axisLabelZ = makeTextSprite('Z', '#6cb6ff');
scene.add(axisLabelX, axisLabelY, axisLabelZ);

/* ---------- AXIS SELECT POPULATION ---------- */
const selX = document.getElementById('sel-x');
const selY = document.getElementById('sel-y');
const selZ = document.getElementById('sel-z');

fields.forEach((f, i) => {
  [selX, selY, selZ].forEach((sel, si) => {
    const opt = document.createElement('option');
    opt.value = f;
    opt.textContent = f;
    if (i === Math.min(si, fields.length - 1)) opt.selected = true;
    sel.appendChild(opt);
  });
});

// Set smarter defaults: pick first three distinct fields
if (fields.length >= 3) {
  selX.value = fields[0];
  selY.value = fields[1];
  selZ.value = fields[2];
} else if (fields.length === 2) {
  selX.value = fields[0];
  selY.value = fields[1];
  selZ.value = fields[0];
} else if (fields.length === 1) {
  selX.value = fields[0];
  selY.value = fields[0];
  selZ.value = fields[0];
}

/* ---------- TIME SLIDER ---------- */
const timeSlider = document.getElementById('time-slider');
const stepDisplay = document.getElementById('step-display');
const playBtn = document.getElementById('play-btn');

const maxStep = Math.max(0, ...trajectories.flatMap(t => t.steps.map(s => s.step)));
timeSlider.max = maxStep;
timeSlider.value = maxStep;

let playing = false;
let playInterval = null;

playBtn.addEventListener('click', () => {
  playing = !playing;
  playBtn.textContent = playing ? '⏸' : '▶';
  if (playing) {
    if (parseInt(timeSlider.value) >= maxStep) timeSlider.value = 0;
    playInterval = setInterval(() => {
      let v = parseInt(timeSlider.value) + 1;
      if (v > maxStep) { v = maxStep; playing = false; playBtn.textContent = '▶'; clearInterval(playInterval); }
      timeSlider.value = v;
      updateScene();
    }, 200);
  } else {
    clearInterval(playInterval);
  }
});

/* ---------- TRAJECTORY MESHES ---------- */
const trajGroup = new THREE.Group();
scene.add(trajGroup);

// We store line objects and point objects per trajectory
let lineObjects = [];
let headObjects = [];
let wildcardMarkers = [];
let pointCloud = null;  // for raycasting hover
let pointData = [];     // metadata per point

function getFieldValue(stepValues, field) {
  return stepValues[field] !== undefined ? stepValues[field] : 0;
}

function computeExtents() {
  const fx = selX.value, fy = selY.value, fz = selZ.value;
  let minV = [Infinity, Infinity, Infinity];
  let maxV = [-Infinity, -Infinity, -Infinity];

  for (const t of trajectories) {
    for (const s of t.steps) {
      const vals = [getFieldValue(s.values, fx), getFieldValue(s.values, fy), getFieldValue(s.values, fz)];
      for (let i = 0; i < 3; i++) {
        if (vals[i] < minV[i]) minV[i] = vals[i];
        if (vals[i] > maxV[i]) maxV[i] = vals[i];
      }
    }
  }

  const ranges = maxV.map((mx, i) => mx - minV[i] || 1);
  const scale = 10;
  return { minV, ranges, scale };
}

function mapPosition(values, ext) {
  const fx = selX.value, fy = selY.value, fz = selZ.value;
  const x = ((getFieldValue(values, fx) - ext.minV[0]) / ext.ranges[0] - 0.5) * ext.scale * 2;
  const y = ((getFieldValue(values, fy) - ext.minV[1]) / ext.ranges[1] - 0.5) * ext.scale * 2;
  const z = ((getFieldValue(values, fz) - ext.minV[2]) / ext.ranges[2] - 0.5) * ext.scale * 2;
  return new THREE.Vector3(x, y, z);
}

function rebuildScene() {
  // Clear
  while (trajGroup.children.length) trajGroup.remove(trajGroup.children[0]);
  lineObjects = [];
  headObjects = [];
  wildcardMarkers = [];
  pointData = [];

  const currentStep = parseInt(timeSlider.value);
  const ext = computeExtents();

  // Axis labels
  axisLabelX.position.set(ext.scale + 1.5, 0, 0);
  axisLabelY.position.set(0, ext.scale + 1.5, 0);
  axisLabelZ.position.set(0, 0, ext.scale + 1.5);

  // Axis lines
  const axMat = [
    new THREE.LineBasicMaterial({ color: 0xf47067, transparent: true, opacity: 0.4 }),
    new THREE.LineBasicMaterial({ color: 0x57ab5a, transparent: true, opacity: 0.4 }),
    new THREE.LineBasicMaterial({ color: 0x6cb6ff, transparent: true, opacity: 0.4 }),
  ];
  const axDirs = [
    [new THREE.Vector3(-ext.scale - 0.5, 0, 0), new THREE.Vector3(ext.scale + 0.5, 0, 0)],
    [new THREE.Vector3(0, -ext.scale - 0.5, 0), new THREE.Vector3(0, ext.scale + 0.5, 0)],
    [new THREE.Vector3(0, 0, -ext.scale - 0.5), new THREE.Vector3(0, 0, ext.scale + 0.5)],
  ];
  for (let i = 0; i < 3; i++) {
    const g = new THREE.BufferGeometry().setFromPoints(axDirs[i]);
    trajGroup.add(new THREE.Line(g, axMat[i]));
  }

  const allPointPositions = [];
  const allPointColors = [];

  for (const traj of trajectories) {
    const color = new THREE.Color(trajColor(traj));
    const visibleSteps = traj.steps.filter(s => s.step <= currentStep);
    if (visibleSteps.length === 0) continue;

    // Line
    const positions = visibleSteps.map(s => mapPosition(s.values, ext));
    if (positions.length >= 2) {
      const lineGeo = new THREE.BufferGeometry().setFromPoints(positions);
      const lineMat = new THREE.LineBasicMaterial({ color, linewidth: 2, transparent: true, opacity: 0.7 });
      const line = new THREE.Line(lineGeo, lineMat);
      trajGroup.add(line);
      lineObjects.push(line);
    }

    // Head sphere at latest visible step
    const headPos = positions[positions.length - 1];
    const headGeo = new THREE.SphereGeometry(0.12, 12, 12);
    const headMat = new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.5 });
    const headMesh = new THREE.Mesh(headGeo, headMat);
    headMesh.position.copy(headPos);
    trajGroup.add(headMesh);
    headObjects.push(headMesh);

    // Points for hover detection
    for (const s of visibleSteps) {
      const p = mapPosition(s.values, ext);
      allPointPositions.push(p.x, p.y, p.z);
      allPointColors.push(color.r, color.g, color.b);
      pointData.push({
        trajectoryId: traj.id,
        outcome: traj.outcome,
        step: s.step,
        values: s.values,
      });
    }
  }

  // Point cloud for raycasting
  if (allPointPositions.length > 0) {
    const pcGeo = new THREE.BufferGeometry();
    pcGeo.setAttribute('position', new THREE.Float32BufferAttribute(allPointPositions, 3));
    pcGeo.setAttribute('color', new THREE.Float32BufferAttribute(allPointColors, 3));
    const pcMat = new THREE.PointsMaterial({ size: 0.08, vertexColors: true, transparent: true, opacity: 0.6, sizeAttenuation: true });
    pointCloud = new THREE.Points(pcGeo, pcMat);
    trajGroup.add(pointCloud);
  } else {
    pointCloud = null;
  }

  // Wildcard markers (red spheres)
  for (const wc of wildcardEvents) {
    if (wc.step > currentStep) continue;
    const traj = trajectories.find(t => t.id === wc.trajectory);
    if (!traj) continue;
    const stepData = traj.steps.find(s => s.step === wc.step);
    if (!stepData) continue;
    const pos = mapPosition(stepData.values, ext);
    const wcGeo = new THREE.SphereGeometry(0.2, 16, 16);
    const wcMat = new THREE.MeshStandardMaterial({
      color: 0xff2222,
      emissive: 0xff2222,
      emissiveIntensity: 0.8,
      transparent: true,
      opacity: 0.85,
    });
    const wcMesh = new THREE.Mesh(wcGeo, wcMat);
    wcMesh.position.copy(pos);
    trajGroup.add(wcMesh);
    wcMesh.userData = { wildcardName: wc.name, step: wc.step, trajectory: wc.trajectory };
    wildcardMarkers.push(wcMesh);
  }

  stepDisplay.textContent = `${currentStep} / ${maxStep}`;
}

function updateScene() {
  rebuildScene();
}

selX.addEventListener('change', updateScene);
selY.addEventListener('change', updateScene);
selZ.addEventListener('change', updateScene);
timeSlider.addEventListener('input', updateScene);

/* ---------- TOOLTIP / HOVER ---------- */
const tooltip = document.getElementById('tooltip');
const raycaster = new THREE.Raycaster();
raycaster.params.Points.threshold = 0.3;
const mouse = new THREE.Vector2();

renderer.domElement.addEventListener('mousemove', (e) => {
  mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
  mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;

  raycaster.setFromCamera(mouse, camera);

  // Check wildcard markers first
  if (wildcardMarkers.length > 0) {
    const wcHits = raycaster.intersectObjects(wildcardMarkers);
    if (wcHits.length > 0) {
      const obj = wcHits[0].object;
      const d = obj.userData;
      tooltip.style.display = 'block';
      tooltip.style.left = (e.clientX + 12) + 'px';
      tooltip.style.top = (e.clientY - 8) + 'px';
      tooltip.querySelector('.tt-title').textContent = `Wildcard: ${d.wildcardName}`;
      tooltip.querySelector('.tt-body').innerHTML =
        `<div class="tt-row">Trajectory: <span>${d.trajectory}</span></div>` +
        `<div class="tt-row">Step: <span>${d.step}</span></div>`;
      return;
    }
  }

  // Check point cloud
  if (pointCloud) {
    const hits = raycaster.intersectObject(pointCloud);
    if (hits.length > 0) {
      const idx = hits[0].index;
      if (idx !== undefined && idx < pointData.length) {
        const d = pointData[idx];
        tooltip.style.display = 'block';
        tooltip.style.left = (e.clientX + 12) + 'px';
        tooltip.style.top = (e.clientY - 8) + 'px';
        tooltip.querySelector('.tt-title').textContent = `Trajectory ${d.trajectoryId} - Step ${d.step}`;

        const fx = selX.value, fy = selY.value, fz = selZ.value;
        let body = `<div class="tt-row">Outcome: <span>${d.outcome}</span></div>`;
        body += `<div class="tt-row">${fx}: <span>${(d.values[fx] ?? 0).toFixed(4)}</span></div>`;
        body += `<div class="tt-row">${fy}: <span>${(d.values[fy] ?? 0).toFixed(4)}</span></div>`;
        body += `<div class="tt-row">${fz}: <span>${(d.values[fz] ?? 0).toFixed(4)}</span></div>`;
        tooltip.querySelector('.tt-body').innerHTML = body;
        return;
      }
    }
  }

  tooltip.style.display = 'none';
});

/* ---------- RESIZE ---------- */
window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

/* ---------- ANIMATE ---------- */
function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}

rebuildScene();
animate();
</script>
</body>
</html>"""


def generate_explorer(run_dir: Path, output_path: Path | None = None) -> Path:
    """Generate interactive 3D explorer HTML. Returns path to output file."""
    run_dir = Path(run_dir)

    data = extract_state_vectors(run_dir)

    if not data["trajectories"]:
        raise ValueError(f"No trajectories found in {run_dir}")

    # Inject data into the HTML template
    data_json = json.dumps(data, indent=None, default=str)
    html = _HTML_TEMPLATE.replace("__DATA_PLACEHOLDER__", data_json)

    if output_path is None:
        output_path = run_dir / "explorer.html"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        f.write(html)

    return output_path
