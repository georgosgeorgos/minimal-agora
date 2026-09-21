# Session Handoff

## Verified Now

- Core engine and features through feat-010 are passing.
- `uv run pytest tests/ -q` — 398 passed, 5 known statistical warnings.
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

## Risks And Tradeoffs

- Numeric extrapolation is intentionally opt-in because discontinuous systems
  may need shorter reasoning intervals or lower drift thresholds.
- Existing scenarios omit `adaptive_steps`, so their behavior is unchanged.
- The test suite still emits five known warnings for degenerate statistical data.

## Next Best Step

- Highest-priority unfinished feature: feat-011, step batching.
- Determine how routine multi-step batches should interact with adaptive steps,
  wildcards, termination checks, and the adversarial review loop before coding.

## Commands

- Startup: `./init.sh`
- Verification: `uv run pytest tests/ -q && uv run ruff check src/ tests/`
- Focused adaptive tests: `uv run pytest tests/test_adaptive_steps.py -q`
