# AGENTS.md

This repository implements **worldsim**, a world simulation engine where LLM
agents debate and interact to explore counterfactual hypotheses and population
dynamics. The goal is not to maximize raw code output. The goal is to leave the
repo in a state where the next session can continue without guessing.

## Repository Structure

| Path | Purpose |
|------|---------|
| `AGENTS.md` | Agent workflow, working rules, session protocol |
| `CLAUDE.md` | Symlink to AGENTS.md |
| `README.md` | Project overview, simulation modes, CLI usage |
| `init.sh` | Standard startup: install deps, run lint + tests |
| `pyproject.toml` | Python project config, dependencies, tool settings |
| `harness-findings.md` | Harness engineering reference (CLI, isolation, patterns) |
| `quality.md` | Quality standards and domain/layer grades |
| `state/features.json` | Source of truth for feature state and verification |
| `state/progress.md` | Session log and current verified status |
| `session/checklist.md` | Session checklist |
| `session/handoff.md` | Session handoff notes |
| `verification/rubric.md` | Evaluator rubric for acceptance review |
| `src/worldsim/` | Core engine: models, board, agents, loop, runner, analysis, CLI |
| `scenarios/examples/` | Example scenario YAML files |
| `tests/` | Pytest test suite |
| `_references/` | Related project references |

## Tech Stack

- **Language**: Python 3.12+
- **Package manager**: uv
- **Models**: Pydantic v2 (strict validation)
- **Config**: YAML scenarios
- **Agent backend**: Claude Code CLI (`claude -p` subprocess)
- **Testing**: pytest
- **Linting**: ruff

## Key Commands

```bash
uv sync --group dev          # Install all dependencies
uv run pytest tests/ -v      # Run test suite
uv run ruff check src/ tests/  # Lint check
uv run worldsim run scenarios/examples/intelligence.yaml -n 3  # Run simulation
```

## Startup Workflow

Before writing code:

1. Confirm the working directory with `pwd`.
2. Read `state/progress.md` for the latest verified state and next step.
3. Read `state/features.json` and choose the highest-priority unfinished feature.
4. Review recent commits with `git log --oneline -5`.
5. Run `./init.sh`.
6. Run `uv run pytest tests/ -v` to verify baseline before starting new work.

If baseline verification is already failing, fix that first. Do not stack new
feature work on top of a broken starting state.

## Working Rules

- Work on one feature at a time.
- Do not mark a feature complete just because code was added.
- Keep changes within the selected feature scope unless a blocker forces a
  narrow supporting fix.
- Do not silently change verification rules during implementation.
- Prefer durable repo artifacts over chat summaries.
- Commit after each atomic change. Do not batch unrelated changes into one commit.
- When starting a new simulation scenario, always ask the user for the setup
  configuration (rules, agents, wildcards, step scale, termination conditions).

## Architecture Overview

### Simulation Modes

| Mode | Purpose | Entity support |
|------|---------|---------------|
| `counterfactual` | N independent runs, statistical answers | flat agents |
| `population` | Interacting entities in shared world, N runs | entities required |
| `open_ended` | Single run optimizing fitness/complexity | either |

### Core Loop (per step)

```
WILDCARD → PROPOSE → CRITIQUE → RESOLVE → UPDATE → CHECK
```

In population mode, propose phase is ordered:
**forces → populations → critics → evaluator**

### Key Modules

| Module | Responsibility |
|--------|---------------|
| `models.py` | Pydantic models: Scenario, AgentConfig, EntityConfig, Proposal, Resolution, etc. |
| `scenario.py` | Load YAML/JSON scenarios, set up workspace directories |
| `board.py` | Board management: state read/write, snapshots, narrative, wildcards |
| `agents.py` | Build role-specific prompts, invoke `claude -p`, parse agent output |
| `loop.py` | Single-trajectory orchestrator: flat step and entity step |
| `runner.py` | Batch runner: parallel trajectories with concurrency control |
| `analysis.py` | Outcome classification, aggregation, report generation |
| `cli.py` | CLI: `run` and `report` subcommands |

### Scenario YAML Structure

```yaml
name: "scenario-name"
mode: counterfactual | population | open_ended
n_trajectories: 10
step_budget: 20
initial_state: { ... }
agents: [ ... ]           # flat mode
entities: [ ... ]          # population mode (population/force/critic/evaluator)
rules: [ ... ]             # domain-specific governing rules
wildcards: [ ... ]         # stochastic external shocks
termination: { ... }
outcome: { ... }           # post-hoc classification
```

## Definition Of Done

A feature is done only when all of the following are true:

- the target behavior is implemented
- `uv run pytest tests/ -v` passes with all tests green
- `uv run ruff check src/ tests/` reports no errors
- evidence is recorded in `state/features.json` or `state/progress.md`
- the repository remains restartable from the standard startup path

## End Of Session

Before ending a session:

1. Update `state/progress.md`.
2. Update `state/features.json`.
3. Record any unresolved risk or blocker.
4. Commit with a descriptive message once the work is in a safe state.
5. Leave the repo clean enough for the next session to run `./init.sh`
   immediately.
