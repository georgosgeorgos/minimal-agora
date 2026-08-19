# Factory Configuration
<!-- This file configures the Remote Factory for your project. -->
<!-- The factory reads this during Init mode and generates .factory/config.json from it. -->

## Goal

A world simulation engine where LLM agents debate and interact to explore counterfactual hypotheses and population dynamics — implement open issues, improve the simulation (make it better/faster), and improve the visualizations.

## Scope

### Modifiable

- src/minimal_agora/**
- tests/**
- scenarios/**
- eval/**

### Read-only

- CLAUDE.md
- AGENTS.md
- README.md
- pyproject.toml

## Guards

- Do not delete or overwrite existing tests
- Do not break the CLI interface (`minimal-agora run`, `minimal-agora report`)
- Do not modify files outside the declared scope
- Do not introduce secrets or credentials into the repository
- Do not modify CLAUDE.md, AGENTS.md, or pyproject.toml structure

## Eval

### Command

```bash
uv run python eval/score.py
```

### Threshold

0.60

## Target Branch

main

## Eval Spec

- name: tests
  command: uv run pytest -v
  weight: 0.4167
  parser: exit_code
  description: Run test suite
  source: discovered

- name: lint
  command: uv run ruff check .
  weight: 0.25
  parser: exit_code
  description: Run linter
  source: discovered

- name: type_check
  command: uv run mypy ./
  weight: 0.125
  parser: exit_code
  description: Run type checker
  source: researched

- name: coverage
  command: uv run pytest --cov=src/minimal_agora --cov-report=term -q
  weight: 0.125
  parser: exit_code
  description: Measure test coverage
  source: researched

- name: observability
  command: (inline)
  weight: 0.0833
  parser: json
  description: Analyze logging coverage, structured logging, and request tracing
  source: researched

## Smoke Test

```bash
uv run pytest tests/ -v
```

## Constraints

- Prefer small, incremental changes over large rewrites
- Each change should be accompanied by at least one test
- Follow the existing code style and conventions
- Work on one feature at a time
- Keep changes within the selected feature scope
- Maintain backward compatibility with existing scenario YAML files

## Project Eval

### test_suite
- command: uv run pytest tests/ -v
- parser: exit_code
- description: Run the full pytest test suite

### test_coverage
- command: uv run pytest --cov=src/minimal_agora --cov-report=term -q
- parser: regex
- pattern: TOTAL.*?(\d+)%
- description: Measure test coverage percentage

## Eval Weights

hygiene: 0.30
growth: 0.20
project: 0.50
