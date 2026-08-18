# Factory Configuration
<!-- This file configures the Remote Factory for your project. -->
<!-- The factory reads this during Init mode and generates .factory/config.json from it. -->

## Goal
<!-- A single sentence describing what this project should achieve. -->

A world simulation engine where LLM agents debate and interact to explore counterfactual hypotheses and population dynamics — implement open issues, improve the simulation (make it better/faster), and improve the visualizations.

## Scope

### Modifiable
<!-- Files and directories the factory is allowed to create or edit. -->

- src/minimal_agora/**
- tests/**
- scenarios/**
- eval/**

### Read-only
<!-- Files the factory may read but must never modify. -->

- CLAUDE.md
- AGENTS.md
- README.md
- pyproject.toml

## Guards
<!-- Rules the factory must never violate. Checked before every commit. -->

- Do not delete or overwrite existing tests
- Do not modify files outside the declared scope
- Do not introduce secrets or credentials into the repository
- Do not modify CLAUDE.md, AGENTS.md, or pyproject.toml structure

## Eval

### Command
<!-- The shell command the factory runs to score a change. -->

```bash
uv run python eval/score.py
```

### Threshold
<!-- Minimum composite score (0.0-1.0) required to keep a change. -->

0.60

## Target Branch
<!-- Branch that experiment PRs target. -->

main

## Project Eval
<!-- User-defined project-specific eval dimensions (benchmarks, accuracy, latency, etc.) -->

## Eval Weights
<!-- Weight distribution across eval tiers (must sum to 1.0) -->
<!-- Default without project eval: hygiene 0.50, growth 0.50 -->

## Eval Spec
<!-- Functional spec checks derived from project analysis. -->
<!-- These are advisory and checked during deep-QA review. -->

- Run the CLI with --help and verify it prints usage information
- Run the CLI with a sample input and verify it produces expected output

## Smoke Test
<!-- Shell command that must pass before any change is kept. -->

```bash
uv run pytest tests/ -v
```

## Constraints
<!-- Soft rules that guide behavior but don't block commits. -->

- Prefer small, incremental changes over large rewrites
- Each change should be accompanied by at least one test
- Follow the existing code style and conventions
- Work on one feature at a time
- Keep changes within the selected feature scope

## Research Target
<!-- Only for research/benchmark projects. Not configured. -->

## Mutable Surfaces
<!-- Files the Builder may modify during research experiments. Not configured. -->

## Fixed Surfaces
<!-- Ground truth files that must not be modified. Not configured. -->

## Research Constraints
<!-- Additional rules for the research loop. Not configured. -->

## Cost Budget
<!-- Per-cycle or total budget constraints. Not configured. -->
