# minimal-agora

A world simulation engine where LLM agents debate and interact to explore
counterfactual hypotheses and population dynamics. Agents propose state
transitions, critics evaluate plausibility, and judges resolve outcomes —
producing trajectories that can be statistically aggregated.

## Simulation Modes

### `counterfactual`

Run the **same scenario N times independently** to answer statistical questions.

Each trajectory is an isolated run with the same agents and initial state but
different random seeds. Wildcards (asteroids, plagues) fire stochastically,
producing different paths. After all trajectories complete, outcomes are
classified and aggregated.

**Use for:** "How frequently does intelligence emerge?" "In what fraction of
runs does Rome fall before 200 AD?"

```
world₁  world₂  world₃  ...  worldₙ     (isolated, same setup)
  ↓       ↓       ↓           ↓
out₁    out₂    out₃        outₙ        → statistics
```

```bash
minimal-agora run scenarios/examples/intelligence.yaml -n 30 -m counterfactual
```

### `population`

Multiple **interacting entities** (civilizations, species, factions) share a
single world. Each entity has its own state subtree and agents. Forces (nature,
disease) modify the shared world. Critics check plausibility. Evaluators score
and resolve.

Run N times to get statistics across population scenarios ("How often does Rome
dominate?"). Each run is a full multi-entity simulation.

**Use for:** "What happens when Rome, Greece, and Persia compete for 1000
years?" "Which civilization dominates under different starting conditions?"

```
         shared world state
         ┌──────┼──────┐
       pop₁   pop₂   pop₃      (interact via shared board)
         └──────┼──────┘
            resolution          → narrative + scores
```

Entity types:

| Type | Role | Owns state | Modifies | Sees |
|------|------|-----------|----------|------|
| `population` | Civilization, species, faction | own subtree | own state + interactions | shared world + own state |
| `force` | Nature, disease, economics | nothing | shared world state | shared world |
| `critic` | Plausibility checker | nothing | nothing (read-only) | everything |
| `evaluator` | Judge, historian, scorer | nothing | scores/rewards | everything post-resolution |

```bash
minimal-agora run scenarios/examples/mediterranean.yaml -n 10 -m population
```

### `open_ended`

Single long-running simulation optimizing for a goal (complexity,
interestingness). Uses a fitness function to measure progress. Can use either
flat agents or entities.

**Use for:** "Evolve the most complex ecosystem possible." "Generate the most
interesting geopolitical timeline."

## Step Loop

Each step follows the same loop regardless of mode:

```
1. WILDCARD  — roll for catastrophic events (asteroid, plague, war)
2. PROPOSE   — actor agents read the board, write proposals
3. CRITIQUE  — critic agents evaluate proposals for plausibility
4. RESOLVE   — judge agent synthesizes into a single resolution
5. UPDATE    — resolution applied to state, narrative appended
6. CHECK     — evaluate termination conditions
```

In population mode, the propose phase runs in order:
**forces → populations → critics → evaluator**.

## Scenario Configuration

Scenarios are YAML files that define everything domain-specific:

```yaml
name: "my-scenario"
mode: counterfactual          # or population, open_ended
n_trajectories: 10
step_budget: 20

initial_state:                # starting world state (JSON-like)
  planet:
    climate: temperate

agents:                       # flat agent list (counterfactual/open_ended)
  - role: actor
    name: natural_selection
    perspective: "You represent..."

entities:                     # typed entities (population mode)
  - name: rome
    type: population
    state_prefix: "populations.rome"
    initial_state:
      military_strength: 60
    agents:
      - role: actor
        name: roman_senate
        perspective: "You represent..."
    can_interact_with: ["greece"]

rules:                        # domain-specific governing rules
  - name: natural_selection
    description: "Evolution operates through variation and selection..."
    applies_to: ["actor"]     # optional: restrict to specific roles/agents

wildcards:                    # stochastic external shocks
  - name: asteroid_impact
    probability: 0.1
    description: "A major asteroid impact..."
    state_impact:
      environment:
        biodiversity: "collapse"

termination:
  max_steps: 20
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

## CLI

```bash
# Run a scenario
minimal-agora run scenario.yaml [options]
  -n, --n-trajectories N    Override number of trajectories
  -m, --mode MODE           Override mode (counterfactual/population/open_ended)
  -c, --concurrency N       Max parallel trajectories (default: 2)
  --steps N                 Override step budget
  --timeout N               Agent timeout in seconds (default: 300)
  -o, --output DIR          Output directory (default: runs/)

# Generate report from completed run
minimal-agora report runs/my-scenario/

# Examples
minimal-agora run scenarios/examples/intelligence.yaml -n 5
minimal-agora run scenarios/examples/mediterranean.yaml -n 3 -m population
minimal-agora run scenarios/examples/intelligence.yaml -n 30 --steps 15
```

## Example Scenarios

- **intelligence.yaml** — Biological evolution on an Earth-like planet.
  Tests how frequently intelligence emerges over 5 billion years.
  Counterfactual mode with natural selection rules and 6 wildcard events.

- **mediterranean.yaml** — Rise of Mediterranean civilizations.
  Rome, Greece, and Persia compete over 1000 years. Population mode with
  environmental forces, historical critic, and Thucydides as judge.

## Requirements

- Python 3.12+
- `claude` CLI (Claude Code) installed and authenticated
- `uv` for dependency management

```bash
uv sync
uv run minimal-agora run scenarios/examples/intelligence.yaml -n 3
```
