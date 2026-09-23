# Code Review — 2026-09-23

## Scope and verification

Reviewed the simulation runner, particle resampling, checkpoint resume path,
project configuration, and repository guidance. The existing suite passed
before changes (415 tests). After changes, 416 tests passed, Ruff check and
format checks passed, and `./init.sh` completed when granted access to the
local uv cache. The first sandboxed startup attempt failed on uv cache access.

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

## Follow-up findings

1. **High — Particle history can disagree with the copied board.**
   `runner.py:186-195` replaces particle workspaces after resampling but keeps
   `all_steps[i]` under the destination index. A copied board can therefore
   have a source particle's state and history files while the returned
   `Trajectory.steps` retains the destination particle's earlier steps.
   Carry the selected parent index into the in-memory step histories and add
   a particle-filter integration test that forces a non-identity resample.

2. **Medium — A resampling event invokes critics twice.**
   `runner.py:165-190` calls `score_particles()` to decide whether ESS crosses
   the threshold, then `resample_particles()` calls the same critics again in
   `resampling.py:126-150`. This adds one provider call per particle and can
   choose parents from scores different from those used for the ESS decision.
   Pass the first score vector into the resampling operation.

3. **Medium — Resume detection assumes contiguous checkpoints.**
   `loop.py:125-130` counts matching full-step files instead of finding the
   last contiguous completed step. If a checkpoint is missing, it can resume
   at the wrong step; `_restore_checkpoint()` then silently skips absent step
   records. Validate the contiguous prefix and the matching state snapshot
   before resuming.

4. **Low — CI type checking cannot fail the build.**
   `.github/workflows/ci.yml:44` ends the mypy command with `|| true`. This
   hides type errors until they surface elsewhere. Make it a required gate
   after the current type errors are triaged.
