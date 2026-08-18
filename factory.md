# Factory Configuration
<!-- This file configures the Remote Factory for your project. -->
<!-- The factory reads this during Init mode and generates .factory/config.json from it. -->

## Goal

Evolve the minimal-agora simulation engine toward production-quality code (type safety, test coverage, observability) and expanded capability surface.

## Scope

### Modifiable

- src/minimal_agora/**/*.py
- tests/**/*.py
- scenarios/**/*.yaml
- eval/**/*.py

### Read-only

- README.md
- pyproject.toml
- CLAUDE.md
- AGENTS.md

## Guards

- Do not delete or overwrite existing tests
- Do not break the CLI interface (`minimal-agora run`, `minimal-agora report`)
- Do not introduce secrets or credentials into the repository
- Do not modify files outside the declared scope

## Eval

### Command

```bash
uv run python eval/score.py
```

### Threshold

0.5

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
  command: uv run pytest --cov= --cov-report=term -q
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
uv run minimal-agora --help
```

## Constraints

- Prefer small, incremental changes over large rewrites
- Each change should be accompanied by at least one test
- Follow the existing code style and conventions
- Maintain backward compatibility with existing scenario YAML files

## Project Eval
<!-- No project-specific eval dimensions configured -->

## Eval Weights
<!-- Default: hygiene 0.50, growth 0.50 (no project eval dimensions) -->
