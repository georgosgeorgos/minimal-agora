# Session Handoff

## Verified Now

- What is currently working:
  - Core engine: models, scenario loading, board management, agent prompt generation, simulation loop, batch runner, analysis, CLI
  - 14 tests passing: scenario loading, workspace setup, deep merge, board resolution, outcome aggregation, report formatting, domain rules, wildcards, entity state merging
  - Clean lint (ruff 0 errors)
  - Two example scenarios: intelligence.yaml (evolution/counterfactual), mediterranean.yaml (population mode)
- What verification actually ran:
  - `uv run pytest tests/ -v` — 14 passed
  - `uv run ruff check src/ tests/` — 0 errors

## Changed This Session

- Code or behavior added:
  - Full minimal-agora engine (8 Python modules in src/minimal-agora/)
  - Three simulation modes: counterfactual, population, open_ended
  - Entity type system: population, force, constraint_evaluator, resolver
  - Domain rules with applies_to filtering
  - Wildcard catastrophic events (6 types in intelligence scenario, 4 in mediterranean)
  - Phased entity execution in population mode (forces → populations → constraint_evaluators → resolver)
  - CLI with -n, -m, --steps overrides
- Infrastructure or harness changes:
  - All harness files updated for minimal-agora (AGENTS.md, init.sh, features.json, progress.md, quality.md, checklist.md, handoff.md, rubric.md)
  - .gitignore updated with __pycache__/, *.pyc, .pytest_cache/, runs/
  - README.md added

## Broken Or Unverified

- Known defect:
  - `_fallback_resolution` in loop.py uses dict.update() instead of _deep_merge — later proposals overwrite earlier ones
  - Wildcard `state_impact` is advisory only, not auto-applied to state
- Unverified path:
  - Full e2e simulation with real Claude CLI (agent invocation never tested against live subprocess)
  - Entity interaction logic (can_interact_with, InteractionConfig) — declared in model, zero runtime implementation
  - open_ended mode fitness tracking — FitnessConfig model exists, nothing reads it
- Risk for the next session:
  - Agent output is fragile: malformed JSON or missing files silently produce None with no retry

## Next Best Step

- Highest-priority unfinished feature: fix-001 (fix _fallback_resolution deep merge)
- Why it is next: It's a bug in existing code, 5 minutes to fix, affects correctness of simulations without a resolver
- What counts as passing: Test showing two proposals with overlapping nested keys both survive in fallback resolution
- What must not change during that step: Existing 14 tests must keep passing

## Commands

- Startup: `./init.sh`
- Verification: `uv run pytest tests/ -v && uv run ruff check src/ tests/`
- Focused debug command: `uv run pytest tests/test_models.py -v -k "test_name"`
