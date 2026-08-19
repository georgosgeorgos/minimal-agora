# Factory Configuration

## Goal

Counterfactual world simulation engine where LLM agents debate and interact to explore hypotheses and population dynamics. Supports counterfactual, population, and open-ended simulation modes with parallel trajectory execution and statistical analysis.

## Scope

### Modifiable

- src/minimal_agora/**/*.py
- tests/**/*.py
- eval/**/*.py
- scenarios/**/*.yaml
- pyproject.toml
- README.md
- CLAUDE.md
- AGENTS.md

### Read-only

- .factory/eval_profile.json
- .factory/eval_spec.json
- state/features.json
- verification/rubric.md

## Guards

- Do not delete or overwrite existing tests
- Do not modify files outside the declared scope
- Do not introduce secrets or credentials into the repository
- Do not modify scenario YAML files that other tests depend on
- Do not remove or weaken Pydantic model validation

## Eval

### Command

```bash
python eval/score.py
```

### Threshold

0.6

## Eval Spec

- Run the CLI with --help and verify it prints usage information
- Run the CLI with a sample input and verify it produces expected output

## Target Branch

main

## Project Eval

### Dimensions

| Dimension | Command | Weight | Parser | Description |
|-----------|---------|--------|--------|-------------|
| tests | `uv run pytest -v` | 0.417 | exit_code | Run test suite |
| lint | `uv run ruff check .` | 0.250 | exit_code | Run linter |
| type_check | `uv run mypy ./` | 0.125 | exit_code | Run type checker |
| coverage | `uv run pytest --cov=src/minimal_agora --cov-report=term -q` | 0.125 | exit_code | Measure test coverage |
| observability | (inline) | 0.083 | json | Analyze logging coverage and structured logging |

## Eval Weights

- Hygiene: 50%
- Growth: 50%

## Hypothesis Budget

- min_growth: 1
- max_new: 2

## Smoke Test

```bash
uv run minimal-agora --help
```

## Test Timeout

300

## Constraints

- Prefer small, incremental changes over large rewrites
- Each change should be accompanied by at least one test
- Follow the existing code style and conventions
- Maintain Pydantic v2 strict validation patterns
- Keep scenario YAML schema backward-compatible
