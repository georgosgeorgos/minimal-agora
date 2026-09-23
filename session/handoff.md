# Session Handoff

## Verified Now

- Core engine and all roadmap features through feat-013 are passing.
- `./init.sh` — 436 passed, 5 known statistical warnings.
- `uv run ruff check src/ tests/` — clean.
- `uv run mypy src/minimal_agora/ --ignore-missing-imports` — no errors.
- All eight example scenarios previously completed 50-step provider validation.
- All eight examples completed fresh three-step, one-trajectory live runs via OpenRouter DeepSeek V4.1 Flash. See `docs/openrouter-deepseek-live-2026-09-23.md`.
- Intelligence and Mediterranean also completed three live trajectories × 20 steps each. See `docs/openrouter-deepseek-3x20-2026-09-23.md` for outcomes and output-quality counts.
- Dashboard can switch between those runs, show outcome and quality summaries, and export a combined static HTML view. README includes the captured dashboard screenshot.
- Historical intelligence particle run is loaded from complete step checkpoints; future particle runs now write `trajectory.json` for normal analysis.
- PR #74 merged as `feef223`; all four CI checks passed. Issue #73 remains open.
- PR #75 merged as `f6a3582`; all four CI checks passed. Issues #73 and #76 remain open.
- A fresh one-step intelligence simulation completed through authenticated Claude CLI with all actor, critic, resolver, checkpoint, and report artifacts.

## Changed This Session

- Added a named `--provider openrouter` CLI route with DeepSeek V4.1 Flash as the
  default model and `OPENROUTER_API_KEY` from the environment.
- Fixed API resampling critics to receive embedded state and narrative, parse
  their stdout scores, and save score files. Scoring now honors the configured
  interval. File-mode critic behavior remains supported.
- Verified the fix with live DeepSeek scoring and completed both requested
  three-trajectory, 20-step examples.
- Added LiteLLM `--disable-reasoning` to avoid exhausting the 2,048-token output
  budget on hidden reasoning in the OpenRouter DeepSeek run.
- Verified all eight example scenarios through OpenRouter with complete step and
  report artifacts; recorded outcomes and usage in the live-validation note.
- Fixed review issues #68–#71 in merged PR #72: particle lineage, duplicate critic
  calls, checkpoint validation, and the CI type-check gate.
- Replaced the README hero reference with a generated, text-free agora image at
  `assets/minima-agora-hero-v2.png`; retained the original JPEG.
- Fixed resampling copy order by staging parents that would be overwritten.
- Consolidated duplicate dev requirements and pytest configuration.
- Updated the repo map and README diagram; added `docs/code-review-2026-09-23.md`.
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

- Mypy uses its existing default scope; it notes that untyped function bodies
  are not checked unless `--check-untyped-defs` is enabled.
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
- Capitalism's live run emitted state-delta schema warnings; the engine applies
  warned changes, so that short run's domain outcome is not trustworthy. Issue #73 tracks this.
- Long runs with DeepSeek still produced malformed actor/resolver JSON. The
  engine continued with missing proposals or fallback resolutions; issue #76
  tracks bounded retries and visible quality counters.
- Mediterranean added new state fields 127 times after schema warnings. No
  original-field type mismatches were logged. Issue #73 covers the policy.
- Historical intelligence particle outputs lack `trajectory.json` files. The
  dashboard reconstructs them from saved full step checkpoints and the run
  summary; the particle runner now saves summaries for future runs.

## Next Best Step

- Address issue #76 (structured-output reliability) and #73 (state-schema
  policy) before relying on long-run outcome distributions.

## Commands

- Startup: `./init.sh`
- Verification: `uv run pytest tests/ -q && uv run ruff check src/ tests/`
- Focused adaptive tests: `uv run pytest tests/test_adaptive_steps.py -q`
- Focused batching tests: `uv run pytest tests/test_step_batching.py -q`
- Focused board-access tests: `uv run pytest tests/test_board_access.py -q`
