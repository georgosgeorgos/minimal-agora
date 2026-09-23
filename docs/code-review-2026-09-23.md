# Code Review — 2026-09-23

## Scope and verification

Reviewed the simulation runner, particle resampling, checkpoint resume path,
project configuration, and repository guidance. The initial review started
with 415 passing tests and ended with 416; Ruff check and format checks passed.
`./init.sh` completed when granted access to the local uv cache. The first
sandboxed startup attempt failed on uv cache access.

## Fixed

- `resampling.py` copied particles in destination order. A later destination
  could read a source already replaced by an earlier copy. Source workspaces
  that may be overwritten are now staged before destination copies. The new
  test covers parent indices `[0, 0, 1]`.
- Removed duplicate development requirements and the redundant `pytest.ini`.
  Pytest settings now live in `pyproject.toml`; the lock metadata reflects the
  same minimum versions.
- Corrected the repository map and added a compact architecture diagram to
  the README. The test badge no longer contains a stale count.

## Findings addressed in [PR #72](https://github.com/georgosgeorgos/minimal-agora/pull/72)

The fixes were verified with 420 passing tests, clean Ruff checks, and a
passing mypy run across 28 source files. The type-check command also failed
as expected when a deliberate type error was introduced temporarily.

1. **High — Particle history can disagree with the copied board.**
   Tracking: [#68](https://github.com/georgosgeorgos/minimal-agora/issues/68).
   `runner.py:186-195` replaces particle workspaces after resampling but keeps
   `all_steps[i]` under the destination index. A copied board can therefore
   have a source particle's state and history files while the returned
   `Trajectory.steps` retains the destination particle's earlier steps.
   Carry the selected parent index into the in-memory step histories and add
   a particle-filter integration test that forces a non-identity resample.
   **Resolved:** The runner now remaps step histories with the chosen parent
   indices. An integration test checks returned steps against copied checkpoint
   files for a non-identity resample.

2. **Medium — A resampling event invokes critics twice.**
   Tracking: [#69](https://github.com/georgosgeorgos/minimal-agora/issues/69).
   `runner.py:165-190` calls `score_particles()` to decide whether ESS crosses
   the threshold, then `resample_particles()` calls the same critics again in
   `resampling.py:126-150`. This adds one provider call per particle and can
   choose parents from scores different from those used for the ESS decision.
   Pass the first score vector into the resampling operation.
   **Resolved:** Parent selection now uses the ESS score vector, and the
   integration test checks one critic invocation per particle.

3. **Medium — Resume detection assumes contiguous checkpoints.**
   Tracking: [#70](https://github.com/georgosgeorgos/minimal-agora/issues/70).
   `loop.py:125-130` counts matching full-step files instead of finding the
   last contiguous completed step. If a checkpoint is missing, it can resume
   at the wrong step; `_restore_checkpoint()` then silently skips absent step
   records. Validate the contiguous prefix and the matching state snapshot
   before resuming.
   **Resolved:** Resume now rejects noncontiguous full-step files, missing
   snapshots, and state mismatches with clear errors.

4. **Low — CI type checking cannot fail the build.**
   Tracking: [#71](https://github.com/georgosgeorgos/minimal-agora/issues/71).
   `.github/workflows/ci.yml:44` ends the mypy command with `|| true`. This
   hides type errors until they surface elsewhere. Make it a required gate
   after the current type errors are triaged.
   **Resolved:** Existing mypy errors were fixed and CI no longer suppresses
   the type-check command's exit status.
