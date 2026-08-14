# Example Scenarios

Each YAML file defines a complete simulation: initial world state, agents,
rules, wildcards, and termination conditions. Agents are `claude -p`
subprocesses differentiated only by their prompt — role, perspective, and
domain rules shape behavior.

All scenarios use realistic step counts (200–1000) for meaningful emergent
dynamics. Use `--steps 10` for quick test runs.

## Wildcards

Wildcards are disabled by default (`wildcards_enabled: false`). Scenarios
that use them must opt in with `wildcards_enabled: true`.

The `probability` field means **expected occurrences per trajectory** — the
engine divides by `max_steps` to get the per-step probability. A wildcard
with `probability: 1.0` fires roughly once per trajectory regardless of
step count.

## Scenarios

### intelligence.yaml — Emergence of Intelligence

**Mode**: counterfactual (5 trajectories)
**Steps**: 500 at 10 million years each (5 billion years)
**Question**: Does intelligent life emerge?

Simulates evolution on a terrestrial planet. Two actor agents (natural
selection, geological forces) propose changes each step. A thermodynamic
critic checks plausibility. A judge synthesizes outcomes.

Six wildcards (asteroid, gamma ray burst, supervolcano, snowball earth, alien
contact, deus ex machina) inject rare catastrophic disruptions (~3 per
trajectory). Five domain rules govern evolutionary dynamics.

```bash
uv run minimal-agora run scenarios/examples/intelligence.yaml -n 10
uv run minimal-agora run scenarios/examples/intelligence.yaml -n 10 --steps 10  # test
```

### mediterranean.yaml — Mediterranean Powers

**Mode**: population (5 trajectories)
**Steps**: 500 at 2 years each (1000 years)
**Question**: Which civilization dominated the Mediterranean?

Three interacting populations (Rome, Greece, Persia) with distinct agents,
strengths, and strategies. Two force entities (nature, disease/migration)
shape the environment. A historian critic checks plausibility. Thucydides
serves as judge.

Populations see each other's state via the interaction system
(`can_interact_with: [...]`, `interaction.mode: always`). Five rules cover
resource competition, cultural influence, military logistics, power vacuums,
and economic incentives.

```bash
uv run minimal-agora run scenarios/examples/mediterranean.yaml -n 5
```

### pandemic.yaml — Pandemic Spread

**Mode**: counterfactual (10 trajectories)
**Steps**: 200 at 1 week each (~4 years)
**Question**: Did coordinated response prevent societal collapse?

Novel pathogen spreading across three regions (East Asia, Europe, Americas).
Three actor agents model disease dynamics, policy response, and social
behavior. An epidemiologist critic grounds proposals in real pandemic data.

Tracks infection rates, healthcare capacity, economic impact, social
cohesion, and vaccine progress. Wildcards include super-spreader events,
mutations, and misinformation waves.

```bash
uv run minimal-agora run scenarios/examples/pandemic.yaml -n 10
```

### market.yaml — Market Competition

**Mode**: population (5 trajectories)
**Steps**: 300 at 1 month each (25 years)
**Question**: Which competitive dynamic prevailed?

Three tech companies (Alpha Corp, Beta Inc, Gamma Labs) compete for market
share, talent, and innovation. A regulator force entity applies antitrust
pressure when concentration grows. Market forces drive talent mobility and
consumer demand shifts.

Rules include capitalistic incentives, network effects, innovation dynamics,
and resource competition. Wildcards: paradigm shift, recession, data breach.

```bash
uv run minimal-agora run scenarios/examples/market.yaml -n 5
```

### complexity.yaml — Complexity Maximizer

**Mode**: open_ended (1 trajectory)
**Steps**: 500 at 10 million years each (5 billion years, wildcards disabled)
**Question**: What level of complexity was achieved?

Fitness-tracked simulation that maximizes biological complexity. The
`life.complexity` metric is evaluated each step. Simulation terminates
when fitness plateaus (no change > 0.5 over 5 steps) or complexity
exceeds 50.

Rules enforce stepwise evolutionary transitions — no skipping from
bacteria to intelligence. Extinction resets complexity but opens niches.

```bash
uv run minimal-agora run scenarios/examples/complexity.yaml
```

### democracy.yaml — Emergence of Democracy

**Mode**: counterfactual (10 trajectories)
**Steps**: 1000 at 5 years each (5000 years, from 3000 BCE)
**Question**: Does liberal democracy become the dominant global governance form?

Simulates political evolution from early agrarian city-states to modern
governance. Three actor agents model political evolution, economic forces,
and cultural/intellectual movements. Tracks governance types across four
regions (Mesopotamia, Mediterranean, East Asia, South Asia) and political
concept milestones (rule of law, representative assembly, individual rights,
separation of powers, universal suffrage).

Democracy is treated as one possible outcome — autocracy, theocracy, and
empire are equally valid endpoints. Wildcards include great conquerors,
revolutionary movements, technological disruptions, and civilizational
collapses.

```bash
uv run minimal-agora run scenarios/examples/democracy.yaml -n 10
```

### capitalism.yaml — Emergence of Capitalism

**Mode**: counterfactual (10 trajectories)
**Steps**: 800 at 5 years each (4000 years, from 2000 BCE)
**Question**: Does market capitalism become the dominant global economic system?

Simulates economic evolution from subsistence agriculture through merchant
economies to potential industrialization. Three actor agents model economic
dynamics, institutional evolution, and technological change. Tracks economic
systems across four regions and concept milestones (private property, wage
labor, capital accumulation, free markets, banking, industrial production).

Capitalism is treated as contingent, not inevitable. Sustained feudalism,
state command economies, and merchant oligarchies are equally valid
endpoints. Wildcards include trade route discoveries, monetary innovations,
economic crises, and state collapses.

```bash
uv run minimal-agora run scenarios/examples/capitalism.yaml -n 10
```

### nuclear_war.yaml — Nuclear War

**Mode**: counterfactual (20 trajectories)
**Steps**: 500 at 1 month each (~42 years, from August 1945)
**Question**: Does nuclear war occur?

Simulates Cold War and post-Cold War nuclear dynamics. Four actor agents
model US strategy, Soviet/Russian strategy, crisis dynamics, and nuclear
proliferation/technology. Tracks arsenals, crisis escalation (0–10 scale),
early warning systems, arms control, and delivery technology evolution.

Higher trajectory count (20) to get stable statistics on a low-probability
catastrophic event. Rules enforce deterrence stability, escalation ladder
dynamics, crisis time pressure, and domestic political constraints.
Wildcards include false alarms, regional crises, leadership changes,
rogue actors, and arms control breakthroughs.

```bash
uv run minimal-agora run scenarios/examples/nuclear_war.yaml -n 20
```

## How Agents Work

All agents are `claude -p` subprocesses. Differentiation is prompt-only:

| Layer | What it controls |
|-------|-----------------|
| **Role** (actor/critic/judge) | Prompt template, output format, execution phase |
| **Perspective** | Domain-specific viewpoint and priorities |
| **Rules** | Filtered by `applies_to` — each agent sees only relevant rules |
| **Interaction** | Population agents see neighbor state when `can_interact_with` allows |
| **Diversity lens** | Rotated per trajectory to prevent mode collapse |

Agents have no persistent memory across steps. The board (`state.json`,
`narrative.md`, proposals, critiques) is their shared context.

## Writing Your Own Scenario

```yaml
name: "your-scenario"
mode: counterfactual | population | open_ended
n_trajectories: 10
step_budget: 500

initial_state:
  # Your domain's starting conditions

agents:           # flat mode (counterfactual/open_ended without entities)
  - role: actor
    name: agent_name
    perspective: "What this agent represents and how it thinks"

entities:         # population mode
  - name: entity_name
    type: population | force | critic | evaluator
    agents: [...]
    can_interact_with: ["other_entity"]
    interaction:
      mode: always | never | scheduled
      every_n_steps: 3    # for scheduled mode

rules:
  - name: rule_name
    description: "What this rule enforces"
    applies_to: ["actor"]  # optional filter

wildcards_enabled: true     # must opt in (default: false)

wildcards:
  - name: event_name
    probability: 1.0        # expected occurrences per trajectory
    description: "What happens"
    state_impact:
      path.to.field: new_value

termination:
  max_steps: 500
  conditions:
    - field: "path.to.field"
      equals: target_value

outcome:
  question: "What are you trying to answer?"
  classifier:
    - name: outcome_name
      condition:
        field: "path.to.field"
        greater_than: 80
    - name: default_outcome
      default: true
```
