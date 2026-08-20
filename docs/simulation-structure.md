# Simulation Structure

How minimal-agora simulations work, from scenario definition through statistical output.

---

## 1. Scenario Definition (YAML)

Everything starts with a scenario file. It declares the world, the agents, the rules, and when to stop.

```yaml
name: "intelligence"
mode: counterfactual        # counterfactual | population | open_ended
n_trajectories: 30          # how many independent runs
step_budget: 500            # max steps per trajectory

initial_state:              # the world at t=0
  planet:
    climate: temperate
    biodiversity: high
  life:
    complexity: unicellular
    intelligence: false

agents:                     # who participates (flat mode)
  - role: actor
    name: natural_selection
    perspective: "You represent evolutionary pressure..."
  - role: actor
    name: environmental_change
    perspective: "You represent geological and climate forces..."
  - role: critic
    name: biologist
    perspective: "You evaluate biological plausibility..."
  - role: judge
    name: historian_of_life
    perspective: "You synthesize competing proposals..."

rules:                      # constraints all agents must obey
  - name: conservation_of_energy
    description: "Energy is neither created nor destroyed..."
    applies_to: [actor]

wildcards_enabled: true
wildcards:                  # stochastic shocks (Poisson-distributed)
  - name: asteroid_impact
    probability: 1.0        # expected occurrences across entire trajectory
    description: "A major asteroid impacts the planet..."
    state_impact:
      planet:
        biodiversity: collapse

review_interval: 3          # skip critic/judge on non-review steps (2-3x speedup)

resampling:                 # particle filter (optional)
  interval: 5               # resample every N steps
  criteria:                 # 10 binary questions scored per trajectory
    - "Did the system state change meaningfully?"
    - "Did a novel entity or dynamic emerge?"
    # ...
  min_particles: 2

termination:
  max_steps: 500
  conditions:
    - field: "life.intelligence"
      equals: true

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

### Simulation Modes

| Mode | What it does | When to use |
|------|-------------|-------------|
| `counterfactual` | N independent runs, same setup, different random seeds. Aggregate outcomes into statistics. | "How often does X happen?" |
| `population` | Multiple interacting entities (civilizations, species) in a shared world. Run N times for statistics. | "Which civilization dominates over 1000 years?" |
| `open_ended` | Single long run optimizing a fitness metric. Stops on plateau. | "How complex can this ecosystem get?" |

### Population Mode Entities

In population mode, `agents` is replaced by `entities` — typed groups with their own state subtrees:

| Type | Role | Example |
|------|------|---------|
| `population` | Civilization, species, faction. Owns and modifies its state subtree. | Rome, Athens |
| `force` | World-level pressure. Modifies shared state. | Climate, disease |
| `critic` | Plausibility checker. Read-only. | Historian, physicist |
| `evaluator` | Judge. Resolves conflicts, scores. | Supreme arbiter |

```yaml
entities:
  - name: rome
    type: population
    state_prefix: "populations.rome"
    initial_state:
      military_strength: 60
      culture: 40
    agents:
      - role: actor
        name: roman_senate
        perspective: "You represent Roman political decisions..."
    can_interact_with: ["greece", "persia"]
```

---

## 2. Workspace Setup

Before simulation starts, `setup_workspace()` creates the filesystem structure each trajectory operates on:

```
trajectory_000/
  board/
    state.json          # current world state (mutated each step)
    narrative.md        # running narrative log
    scenario.md         # human-readable scenario description
    wildcard_step_NNN.json  # active wildcard (if any)
  proposals/            # actor outputs per step
  critiques/            # critic outputs per step
  resolutions/          # judge outputs per step
  history/              # step snapshots for checkpointing
    step_000_state.json
    step_000_full.json
  trajectory.json       # final trajectory record
```

The `Board` class manages all reads/writes to this workspace. All writes use **atomic operations** (tempfile + fsync + rename) to survive crashes mid-step.

---

## 3. The Core Loop

Every simulation step follows the same structure. The only difference between modes is how agents are organized.

### Flat Mode (counterfactual / open_ended)

```
For each step:

1. WILDCARD — Roll for stochastic shocks (Poisson per step).
   If triggered: write wildcard file, apply state_impact to state.json

2. PROPOSE — All actors run in parallel.
   Each receives: current state + narrative + wildcard + rules + perspective
   Each returns: {proposed_changes, reasoning, confidence}
   Proposals are parsed from stdout (inline JSON, single inference call)

3. CRITIQUE — All critics run in parallel (on review steps only)
   Each receives: state + narrative + all proposals + wildcard
   Each returns: {assessment, plausibility, issues}

4. RESOLVE — Single judge synthesizes everything
   Receives: state + narrative + all proposals + all critiques + wildcard
   Returns: {state_delta, narrative, reasoning}

5. UPDATE — Deep-merge state_delta into state.json
   Append narrative. Snapshot to history/.

6. CHECK — Evaluate termination conditions against updated state.
   If met: stop trajectory. If open_ended: also check fitness plateau.
```

### Review Interval Optimization

Not every step needs a full critique + judge pass. With `review_interval: 3`:

```
Step 0:  WILDCARD -> PROPOSE -> CRITIQUE -> RESOLVE -> UPDATE   (full review)
Step 1:  WILDCARD -> PROPOSE -> auto-merge proposals -> UPDATE  (fast)
Step 2:  WILDCARD -> PROPOSE -> auto-merge proposals -> UPDATE  (fast)
Step 3:  WILDCARD -> PROPOSE -> CRITIQUE -> RESOLVE -> UPDATE   (full review)
```

On non-review steps, all actor proposals are deep-merged directly into state without critic/judge evaluation. The last step is always a review step.

### Population Mode

Same loop, but the propose phase runs in entity order:

```
1. Forces propose (world-level changes, in parallel)
2. Populations propose (entity-level changes, in parallel, with interaction context)
3. Critics evaluate all proposals (in parallel)
4. Evaluator/judge resolves everything
```

Each population agent receives **interaction context** — the visible state of entities it `can_interact_with`. This creates cross-entity dynamics (trade, war, competition) without direct agent-to-agent communication.

---

## 4. Agent Invocation

Agents are stateless LLM calls. No memory, no fine-tuning, no agent frameworks.

### Prompt Structure (Inline Mode)

The prompt embeds everything the agent needs — no tool calls, no file reads:

```
You are **natural_selection**, an actor agent in a world simulation.

## Your Perspective
You represent evolutionary pressure operating on biological systems...

## Simulation Step 42

## Current World State
```json
{"planet": {"climate": "temperate"}, "life": {"complexity": "multicellular"}}
```

## Narrative History
## Step 1
Early chemical reactions produced self-replicating molecules...
## Step 2
...

## Governing Rules
**conservation_of_energy**: Energy is neither created nor destroyed...

## Active Wildcard Event
**asteroid_impact**: A major asteroid impacts the planet...
This is a major external shock that MUST be accounted for in your proposal.

## Instructions
Respond with ONLY a JSON object (no markdown fences):
{"agent": "natural_selection", "role": "actor", "proposed_changes": {...},
 "reasoning": "...", "confidence": 0.7}
```

### Provider Abstraction

The same prompt is sent through a pluggable provider:

| Provider | How it works | Latency |
|----------|-------------|---------|
| `ClaudeSubprocessProvider` | `claude -p <prompt> --max-turns 1` | ~5-15s per call |
| `AnthropicAPIProvider` | Direct API via `anthropic.AsyncAnthropic` | ~3-10s per call |
| `MockProvider` | Returns deterministic JSON. For testing. | <1ms |

With `--max-turns 1` and inline state, each agent call is a **single inference** — no tool use, no multi-turn conversation.

### Concurrency Control

Agents within a step run in parallel via `asyncio.TaskGroup`, bounded by a semaphore:

```python
agent_semaphore = asyncio.Semaphore(scenario.max_concurrent_agents)  # default: 8
```

Trajectories also run in parallel (in batch mode), with a separate concurrency limit:

```python
trajectory_semaphore = asyncio.Semaphore(concurrency)  # default: 4
```

---

## 5. State Management

### State Delta Application

The judge returns a `state_delta` — a partial dict of changes. This is **deep-merged** into the current state:

```python
state_delta = {"life": {"complexity": "multicellular"}}
# + existing state {"life": {"intelligence": false, "complexity": "unicellular"}}
# = merged state   {"life": {"intelligence": false, "complexity": "multicellular"}}
```

Dotted paths (`"life.complexity": "multicellular"`) are expanded before merging, so agents can use either flat or nested notation.

### Checkpointing

After every step:
- `state.json` is overwritten (atomic write)
- `history/step_NNN_state.json` snapshot saved
- `history/step_NNN_full.json` complete Step record saved (proposals, critiques, resolution, state_before, state_after)

On crash, resume detects the last completed step and restores from checkpoint.

### Wildcards

Each step rolls against every wildcard's per-step probability:

```python
per_step_probability = event.probability / max_steps
```

A wildcard with `probability: 1.0` over 500 steps fires with ~0.2% chance per step (expected: 1 occurrence per trajectory). When triggered:
1. The wildcard's `state_impact` is merged into state immediately
2. The wildcard dict is embedded in all agent prompts for that step
3. Agents must account for it in their proposals

---

## 6. Particle Filter (Sequential Importance Resampling)

Optional. Activated by setting `resampling` in the scenario.

### How It Works

Instead of running N trajectories independently, the particle filter runs all N trajectories **step-synchronized** and periodically resamples — killing boring trajectories and forking interesting ones.

```
Step 0-4:  All N trajectories run normally (one step at a time, in parallel)

Step 5:    RESAMPLE
           1. Score each trajectory on 10 binary criteria
           2. Compute importance weights (Laplace-smoothed)
           3. Systematic resampling: select N parents from N trajectories
           4. Fork high-weight workspaces, overwrite low-weight ones

Step 6-9:  All N trajectories continue from their (possibly forked) state

Step 10:   RESAMPLE again
           ...
```

### Scoring

A resampling critic agent evaluates each trajectory against scenario-specific criteria:

```yaml
criteria:
  - "Did the system state change meaningfully this period?"
  - "Did a novel entity, force, or dynamic emerge?"
  - "Is there active conflict or tension between forces?"
  - "Did complexity increase?"
  - "Did an unexpected or surprising event occur?"
  # ... (10 total)
```

Each criterion gets a 0 or 1. The total score (0-10) becomes the trajectory's raw weight.

### Weight Computation

```python
# Laplace smoothing: add 1 to every score so nothing has zero weight
raw_weights = [score.total + 1 for score in scores]
normalized = [w / sum(raw_weights) for w in raw_weights]
```

### Systematic Resampling

Standard particle filter resampling. Places N evenly-spaced points on [0,1] and selects parents by CDF:

```python
def systematic_resample(weights, n):
    cumsum = cumulative_sum(weights)
    step = 1.0 / n
    u = step * 0.5  # start at half-step
    indices = []
    for _ in range(n):
        find index where cumsum[index] >= u
        indices.append(index)
        u += step
    return indices
```

A trajectory scoring 8/10 might get 3 copies; one scoring 1/10 might be eliminated entirely.

### Workspace Forking

When trajectory B is selected to replace trajectory A:

```python
shutil.copytree(workspace_B, workspace_A)  # full filesystem copy
```

The forked trajectory continues from B's state but with A's index. This preserves the total particle count while concentrating compute on promising paths.

---

## 7. Batch Execution

### Standard Batch (`run_batch`)

All N trajectories run fully independently with bounded concurrency:

```
trajectory_0  ●━━━━━━━━━━━━━━━━━━━━━━━━━━● done
trajectory_1  ●━━━━━━━━━━━━━━━━━━━━━━● done
trajectory_2          ●━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━● done
trajectory_3                  ●━━━━━━━━━━━━━━━━━━━━━● done
              └─ semaphore limits concurrent trajectories ─┘
```

Each trajectory runs to completion or termination independently. No cross-trajectory communication.

### Particle Filter Batch (`run_particle_filter`)

All N trajectories are step-synchronized:

```
              step 0    step 1    step 2    step 3    step 4    RESAMPLE    step 5 ...
trajectory_0  ●─────────●─────────●─────────●─────────●─────────┤           ●────── ...
trajectory_1  ●─────────●─────────●─────────●─────────●─────────┤ score &   ●────── ...
trajectory_2  ●─────────●─────────●─────────●─────────●─────────┤ resample  ●────── ...
trajectory_3  ●─────────●─────────●─────────●─────────●─────────┤           ●────── ...
                                                                barrier
```

All trajectories complete step N before any starts step N+1. Resampling happens at the barrier.

---

## 8. Outcome Classification

After a trajectory completes (termination condition met or step budget exhausted), its final state is classified:

```yaml
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

The classifier checks conditions in order. First match wins. If nothing matches, the `default: true` entry is used.

---

## 9. Statistical Analysis

After all trajectories complete, outcomes are aggregated:

### Aggregate Report

```
=== intelligence ===
Question: Did intelligent life emerge?
Trajectories: 30

Outcomes:
  intelligent_life: 8/30 (26.7%)  mean steps: 342.5
  stagnation: 22/30 (73.3%)      mean steps: 500.0
```

With confidence intervals (bootstrap, 9999 resamples) and Monte Carlo standard errors.

### Cross-Run Comparison

Compare two runs (e.g., with vs. without wildcards):

| Metric | Method |
|--------|--------|
| Outcome proportions | Two-proportion z-test (statsmodels) |
| Confidence intervals | Bootstrap (scipy) |
| Effect size | Cohen's d with pooled standard deviation |

```python
compare_runs(trajectories_a, trajectories_b, alpha=0.05)
# -> CrossRunComparison with p-values, effect sizes, significance flags
```

### Convergence Detection

If >80% of trajectories produce the same outcome, a warning is raised:

```
Possible mode collapse: 28/30 (93%) trajectories classified as 'stagnation'.
Consider increasing prompt diversity or adding wildcard events.
```

---

## 10. Data Flow Summary

```
scenario.yaml
    │
    ▼
┌──────────────────┐
│  setup_workspace  │  Create board/, proposals/, critiques/, resolutions/, history/
└──────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Per trajectory (N times, in parallel or step-synchronized)         │
│                                                                      │
│  For each step:                                                      │
│    ┌─────────┐    ┌─────────────┐    ┌──────────┐    ┌────────────┐ │
│    │ Wildcard │───▶│ Actors (||) │───▶│ Critics  │───▶│   Judge    │ │
│    │ (random) │    │ propose     │    │ evaluate │    │ synthesize │ │
│    └─────────┘    └─────────────┘    └──────────┘    └────────────┘ │
│                         │                                  │         │
│                         ▼                                  ▼         │
│                    proposals/              state_delta + narrative    │
│                                                    │                 │
│                                          ┌─────────▼──────────┐     │
│                                          │ deep_merge(state)   │     │
│                                          │ snapshot to history/ │     │
│                                          │ check termination   │     │
│                                          └────────────────────┘     │
│                                                                      │
│  [If particle filter: RESAMPLE every N steps]                        │
│    score trajectories -> compute weights -> systematic resample      │
│    fork interesting workspaces, kill boring ones                      │
│                                                                      │
│  On completion: classify outcome from final state                    │
└──────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────┐
│ aggregate_outcomes│  Count outcomes, compute rates, CIs, SEs
└──────────────────┘
    │
    ▼
┌──────────────────┐
│ report / compare │  Text report, JSON export, cross-run z-tests
└──────────────────┘
```

---

## 11. Key Design Decisions

**Agents are stateless.** Every agent call gets the full context in its prompt. No conversation history, no memory. This makes calls embarrassingly parallel and crash-resumable.

**Filesystem as shared memory.** Agents don't talk to each other. They read from and write to a shared workspace (the "board"). The loop orchestrates turn order. This eliminates coordination bugs and makes the system debuggable — you can inspect any step's state by reading the files.

**Structured disagreement over monologue.** Multiple agents with different perspectives propose, then critics filter, then a judge resolves. This produces better trajectories than a single agent generating everything, because bad proposals get caught before they affect state.

**Monte Carlo over single runs.** Running the same scenario 30+ times with stochastic variation (wildcards, diversity lenses) and aggregating produces statistical answers: "intelligence emerges 27% of the time" rather than "intelligence emerged" (sample of one).

**Particle filtering over uniform sampling.** When most trajectories are boring (stagnation), the particle filter concentrates compute on interesting paths by killing low-scoring trajectories and forking high-scoring ones. Same total compute, better coverage of the outcome space.
