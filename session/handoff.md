# Session Handoff

## Verified Now

- Core engine and features through feat-011 are passing.
- `uv run pytest tests/ -q` — 408 passed, 5 known statistical warnings.
- `uv run ruff check src/ tests/` — clean.
- All eight example scenarios previously completed 50-step provider validation.

## Changed This Session

- Fixed `test_review_interval_skip` so it mocks the current provider-return seam;
  this prevents a unit test from invoking the real Claude subprocess.
- Added opt-in adaptive step execution through `Scenario.adaptive_steps`.
- Routine steps repeat numeric leaf deltas from the latest reasoned step without
  making LLM calls.
- Full reasoning remains mandatory on the first and final steps, wildcard steps,
  cadence checkpoints, and configured state-drift thresholds.
- Steps persist `execution_mode`; trajectories persist reasoned/routine/skipped
  counts under `metadata.adaptive_steps`.
- Particle-filter runs now use the shared `_run_step` execution seam.
- Added opt-in flat-scenario step batching with one provider call per role for
  multiple simulated periods.
- Batched periods retain individual proposals, critiques, resolutions, state
  snapshots, termination checks, and token accounting.
- Unsupported combinations fail validation instead of silently weakening
  wildcard, population, resampling, or adaptive-step semantics.

## Risks And Tradeoffs

- Numeric extrapolation is intentionally opt-in because discontinuous systems
  may need shorter reasoning intervals or lower drift thresholds.
- Existing scenarios omit `adaptive_steps`, so their behavior is unchanged.
- Existing scenarios also omit `step_batching`, so batching is opt-in.
- Batching currently excludes population entities, enabled wildcards,
  resampling, and simultaneous adaptive steps.
- The test suite still emits five known warnings for degenerate statistical data.

## Next Best Step

- Highest-priority unfinished feature: feat-012, configurable state-in-prompt
  versus file-based board interaction.
- Preserve the current one-round-trip embedded-state path as the default and
  define an explicit compatibility/test matrix before adding another mode.

## Commands

- Startup: `./init.sh`
- Verification: `uv run pytest tests/ -q && uv run ruff check src/ tests/`
- Focused adaptive tests: `uv run pytest tests/test_adaptive_steps.py -q`
- Focused batching tests: `uv run pytest tests/test_step_batching.py -q`
