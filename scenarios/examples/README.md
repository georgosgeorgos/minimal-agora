# Example Scenarios

Each YAML file defines a complete simulation: initial world state, agents,
rules, wildcards, and termination conditions. Agents are `claude -p`
subprocesses differentiated only by their prompt — role, perspective, and
domain rules shape behavior.

## Scenarios

### intelligence.yaml — Emergence of Intelligence

**Mode**: counterfactual (5 trajectories)
**Step scale**: 100 million years
**Question**: Does intelligent life emerge?

Simulates 4.5 billion years of evolution on a terrestrial planet. Two actor
agents (natural selection, geological forces) propose changes each step. A
thermodynamic critic checks plausibility. A judge synthesizes outcomes.

Six wildcards (asteroid, gamma ray burst, supervolcano, snowball earth, alien
contact, deus ex machina) inject catastrophic disruptions. Five domain rules
govern evolutionary dynamics.

```bash
uv run worldsim run scenarios/examples/intelligence.yaml -n 10
```

### mediterranean.yaml — Mediterranean Powers

**Mode**: population (5 trajectories)
**Step scale**: 50 years
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
uv run worldsim run scenarios/examples/mediterranean.yaml -n 5
```

### complexity.yaml — Complexity Maximizer

**Mode**: open_ended (1 trajectory)
**Step scale**: 200 million years
**Question**: What level of complexity was achieved?

Fitness-tracked simulation that maximizes biological complexity. The
`life.complexity` metric is evaluated each step. Simulation terminates
when fitness plateaus (no change > 0.5 over 5 steps) or complexity
exceeds 50.

Rules enforce stepwise evolutionary transitions — no skipping from
bacteria to intelligence. Extinction resets complexity but opens niches.

```bash
uv run worldsim run scenarios/examples/complexity.yaml
```

### pandemic.yaml — Pandemic Spread

**Mode**: counterfactual (10 trajectories)
**Step scale**: 1 month
**Question**: Did coordinated response prevent societal collapse?

Novel pathogen spreading across three regions (East Asia, Europe, Americas).
Three actor agents model disease dynamics, policy response, and social
behavior. An epidemiologist critic grounds proposals in real pandemic data.

Tracks infection rates, healthcare capacity, economic impact, social
cohesion, and vaccine progress. Wildcards include super-spreader events,
mutations, and misinformation waves.

```bash
uv run worldsim run scenarios/examples/pandemic.yaml -n 10
```

### market.yaml — Market Competition

**Mode**: population (5 trajectories)
**Step scale**: 1 fiscal quarter
**Question**: Which competitive dynamic prevailed?

Three tech companies (Alpha Corp, Beta Inc, Gamma Labs) compete for market
share, talent, and innovation. A regulator force entity applies antitrust
pressure when concentration grows. Market forces drive talent mobility and
consumer demand shifts.

Rules include capitalistic incentives, network effects, innovation dynamics,
and resource competition. Wildcards: paradigm shift, recession, data breach.

```bash
uv run worldsim run scenarios/examples/market.yaml -n 5
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
step_budget: 20

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

wildcards:
  - name: event_name
    probability: 0.1
    description: "What happens"
    state_impact:
      path.to.field: new_value

termination:
  max_steps: 20
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
