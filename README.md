# minimal-agora

<p align="center">
  <img src="assets/minima-agora-image.jpeg" alt="Minimal Agora — LLM agents debate in a Greek agora" width="800">
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.12%2B-blue.svg" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/tests-387%20passing-brightgreen.svg" alt="Tests: 387 passing">
  <img src="https://img.shields.io/badge/lint-ruff-orange.svg" alt="Lint: ruff">
  <img src="https://img.shields.io/badge/scenarios-8%20validated-purple.svg" alt="Scenarios: 8 validated">
</p>

A world simulation engine where LLM agents debate and interact to explore
counterfactual hypotheses and population dynamics.

---

## Why

History happened once. We can't rerun the Peloponnesian War or the Cold War
to see what would have changed. minimal-agora treats historical and
scientific questions as Monte Carlo problems: run the same scenario hundreds
of times with stochastic shocks and independent agent reasoning, then
aggregate outcomes into statistical answers.

The core idea is **structured disagreement**. Each simulation step forces
multiple agents — with different perspectives and domain expertise — to
propose what happens next. A conflict-gated resolution system merges
consistent proposals automatically and invokes a resolver only when actors
disagree. This produces more plausible trajectories than any single prompt
could.

Agents are stateless. They share context through a filesystem board
(state, narrative, proposals). No fine-tuning, no memory, no agent
frameworks — just prompts, roles, and domain rules.

---

## Installation

```bash
git clone https://github.com/georgosgeorgos/minimal-agora.git
cd minimal-agora
uv sync --group dev
uv run pytest tests/ -v
```

**Requirements:** Python 3.12+, [uv](https://docs.astral.sh/uv/)

---

## Provider Setup

minimal-agora supports three LLM backends. Pick one:

### Anthropic API (recommended)

```bash
cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY=sk-ant-...

uv run minimal-agora run scenarios/examples/pandemic.yaml -n 3 --steps 10 \
  --provider anthropic
```

Works with any Anthropic-compatible endpoint (including LiteLLM proxies).
Set `ANTHROPIC_BASE_URL` in `.env` for custom endpoints.

### LiteLLM (multi-provider)

```bash
uv pip install 'minimal-agora[litellm]'

uv run minimal-agora run scenarios/examples/pandemic.yaml -n 3 --steps 10 \
  --provider litellm --model openai/gpt-4o --api-key sk-...
```

Supports 100+ providers via [LiteLLM](https://docs.litellm.ai/docs/providers).

### Claude CLI subprocess (default)

```bash
# Requires Claude Code CLI installed and authenticated
uv run minimal-agora run scenarios/examples/pandemic.yaml -n 3 --steps 10
```

### Environment variables

All credentials go in `.env` (gitignored):

| Variable | Provider | Purpose |
|----------|----------|---------|
| `ANTHROPIC_API_KEY` | anthropic | API key |
| `ANTHROPIC_BASE_URL` | anthropic | Custom endpoint URL |
| `HTTPS_PROXY` | any | Route through a proxy |

CLI flags `--api-key` and `--api-base` override env vars.

---

## Quick Start

```bash
# Run a simulation
uv run minimal-agora run scenarios/examples/intelligence.yaml \
  -n 3 --steps 10 --provider anthropic

# View results
uv run minimal-agora report

# Generate interactive dashboard
uv run minimal-agora dashboard --static --open
```

---

## Architecture

### Core Simulation Loop

Each step follows a conflict-gated loop:

```
PROPOSE (actors in parallel)
    |
    v
detect_conflicts()
    |
    +-- No conflicts, not review step --> auto-merge (0 LLM calls)
    |
    +-- Conflicts detected --> resolver only (1 LLM call)
    |
    +-- Review step --> constraint_evaluator + resolver (2 LLM calls)
```

In population mode, the propose phase is ordered:
**forces --> populations --> constraint_evaluators --> resolver**

### Simulation Modes

| Mode | Purpose | Use case |
|------|---------|----------|
| `counterfactual` | N independent runs, statistical answers | "Does intelligence emerge?" |
| `population` | Interacting entities in shared world | "Which civilization dominates?" |
| `open_ended` | Single run optimizing fitness/complexity | "Maximize ecosystem complexity" |

---

## Scenarios

8 validated example scenarios spanning biology, geopolitics, economics, and epidemiology:

| Scenario | Mode | Steps | Step scale | Question |
|----------|------|-------|------------|----------|
| `intelligence` | counterfactual | 500 | 10M years | Does intelligent life emerge? |
| `mediterranean` | population | 500 | 2 years | Which civilization dominates? |
| `pandemic` | counterfactual | 200 | 1 week | Does coordinated response prevent collapse? |
| `market` | population | 300 | 1 month | Which competitive dynamic prevails? |
| `complexity` | open_ended | 500 | 10M years | What complexity level is achieved? |
| `democracy` | counterfactual | 1000 | 5 years | Does liberal democracy emerge? |
| `capitalism` | counterfactual | 800 | 5 years | Does market capitalism emerge? |
| `nuclear_war` | counterfactual | 500 | 1 month | Does nuclear war occur? |

```bash
# Quick test run
uv run minimal-agora run scenarios/examples/pandemic.yaml -n 3 --steps 10 --provider anthropic

# Full run
uv run minimal-agora run scenarios/examples/nuclear_war.yaml -n 20 --provider anthropic

# Batch all scenarios
./scripts/run-validate.sh          # 50 steps each
./scripts/run-all.sh               # full step budgets
```

---

## Visualization

Three standalone HTML outputs per run — no server required, sharable as single files.

### Dashboard

Full simulation dashboard with Chart.js: field timelines, wildcard heatmap,
agent activity, token usage, event log. Dark/light toggle.

```bash
minimal-agora dashboard runs/nuclear-war --static --open
```

### Interactive Report

Plotly interactive charts: outcome distributions, 3D state-space trajectories,
field timelines, resolution path visualization, constraint evaluator scores,
agent calibration, outcome coverage.

```bash
minimal-agora explore runs/nuclear-war --open
```

### 3D State-Space Explorer

Three.js 3D view of trajectory paths. Axis picker dropdowns, time scrubber
with play/pause, orbit controls, wildcard markers. Trajectories colored by outcome.

```bash
minimal-agora explore-3d runs/nuclear-war --open
```

### Analysis CLI

```bash
minimal-agora calibration runs/nuclear-war    # agent acceptance rates, confidence calibration
minimal-agora coverage runs/nuclear-war       # outcome entropy, trajectory divergence
minimal-agora report runs/nuclear-war         # outcome summary
```

---

## Scenario Configuration

```yaml
name: "my-scenario"
mode: counterfactual
n_trajectories: 10
step_budget: 200
review_interval: 5              # constraint evaluation every N steps
temperature_start: 1.0          # exploratory early...
temperature_end: 0.5            # ...conservative late

initial_state:
  world:
    climate: temperate

agents:
  - role: actor
    name: natural_selection
    perspective: "You represent evolutionary forces..."
  - role: actor
    name: geological_forces
    perspective: "You represent geological processes..."
  - role: constraint_evaluator  # optional: periodic plausibility check
    name: physics_check
    perspective: "You enforce physical constraints..."
  - role: resolver
    name: arbiter
    perspective: "You synthesize proposals into outcomes..."

rules:
  - name: conservation_of_energy
    description: "Energy cannot be created or destroyed"
    applies_to: ["actor"]

wildcards_enabled: true
wildcards:
  - name: asteroid_impact
    probability: 1.0            # expected occurrences per trajectory
    description: "A major asteroid impact"
    state_impact:
      environment:
        biodiversity: "collapse"

outcome:
  question: "Did intelligent life emerge?"
  classifier:
    - name: intelligent_life
      condition:
        field: "life.intelligence"
        equals: true
    - name: stagnation
      default: true
```

---

## CLI Reference

```bash
# Simulation
minimal-agora run <scenario.yaml> [-n N] [--steps N] [-c N] [--provider ...] [--model ...]
minimal-agora validate <scenario.yaml>
minimal-agora init-scenario <name> [--mode ...]
minimal-agora agents <scenario.yaml>

# Analysis
minimal-agora report [run_dir] [--format text|json]
minimal-agora calibration [run_dir] [--format text|json]
minimal-agora coverage [run_dir] [--format text|json]
minimal-agora compare <dir_a> <dir_b> [--alpha 0.05]

# Visualization
minimal-agora dashboard [run_dir] [--static] [--open] [-p PORT]
minimal-agora explore [run_dir] [--fields ...] [--open]
minimal-agora explore-3d [run_dir] [--open]
minimal-agora visualize [run_dir] [--types ...] [--fields ...]
```

---

## Features

- **Three simulation modes** — counterfactual, population, open-ended
- **Conflict-gated resolution** — auto-merge when actors agree, resolver when they conflict, full evaluation on review steps
- **Pluggable LLM providers** — Anthropic API, LiteLLM (100+ models), Claude CLI subprocess
- **Multi-model routing** — different models per agent role
- **Temperature scheduling** — exploratory early, conservative late
- **Adaptive review interval** — trigger evaluation when state changes significantly
- **Atomic checkpointing** — crash-safe writes, resume from any step
- **Particle filtering** — sequential importance resampling across trajectories
- **Statistical analysis** — z-test, bootstrap CIs, Cohen's d, cross-run comparison
- **Agent calibration tracking** — acceptance rates, confidence calibration, plausibility scores
- **Outcome coverage metrics** — Shannon entropy, trajectory divergence, PCA projection
- **Three visualization outputs** — Chart.js dashboard, Plotly interactive report, Three.js 3D explorer
- **Structured logging** — structlog with JSON/console rendering

---

## Documentation

- [Design Guide](docs/guide.md) — architecture, configuration, flow diagrams
- [Simulation Structure](docs/simulation-structure.md) — detailed internals
- [Example Scenarios](scenarios/examples/) — 8 ready-to-run scenarios with validation results

---

## License

[MIT](LICENSE)
