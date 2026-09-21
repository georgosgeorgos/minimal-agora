# Session Handoff

## Verified Now

- Core engine and all roadmap features through feat-012 are passing.
- `uv run pytest tests/ -q` — 415 passed, 5 known statistical warnings.
- `uv run ruff check src/ tests/` — clean.
- All eight example scenarios previously completed 50-step provider validation.
- A fresh one-step intelligence simulation completed through authenticated Claude CLI with all actor, critic, resolver, checkpoint, and report artifacts.

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
- Added scenario-level `board_access: embedded|files`; embedded remains the
  backward-compatible default.
- Centralized prompt context and output parsing so flat and population loops
  use the same access-mode policy.
- File mode requires a workspace-capable provider, omits board state from
  prompts, and treats artifact files as authoritative.
- Providers now declare workspace-I/O capability; invalid configurations fail
  before simulation work begins.
- Claude subprocesses default to five turns for workspace reads/writes, and
  file mode rejects configured budgets below three turns.
- Added seven board-access tests and documented the compatibility matrix.

## Risks And Tradeoffs

- Numeric extrapolation is intentionally opt-in because discontinuous systems
  may need shorter reasoning intervals or lower drift thresholds.
- Existing scenarios omit `adaptive_steps`, so their behavior is unchanged.
- Existing scenarios also omit `step_batching`, so batching is opt-in.
- Batching currently excludes population entities, enabled wildcards,
  resampling, and simultaneous adaptive steps.
- File-based board access currently excludes step batching because batching's
  multi-period response contract is stdout based.
- File mode is currently supported by the Claude subprocess provider; API,
  LiteLLM, and mock providers do not have workspace tool access.
- The configured RITS GLM-5.2 endpoint returned HTTP 503 during the latest
  attempted run; authenticated Claude CLI validation succeeded afterward.
- The test suite still emits five known warnings for degenerate statistical data.

## Next Best Step

- No roadmap features are unfinished. Select the next roadmap item through an
  issue before implementation.

## Commands

- Startup: `./init.sh`
- Verification: `uv run pytest tests/ -q && uv run ruff check src/ tests/`
- Focused adaptive tests: `uv run pytest tests/test_adaptive_steps.py -q`
- Focused batching tests: `uv run pytest tests/test_step_batching.py -q`
- Focused board-access tests: `uv run pytest tests/test_board_access.py -q`
