---
tags: [factory, experiment, minimal-agora]
project: minimal-agora
experiment_id: 001
verdict: revert
score_delta: +0.006
date: 2026-08-18
source: factory-archivist
---

# Experiment #001: Fix resampling critic — migrate to inline prompts (Issue #40)

## Result
**REVERT** — score changed from 0.543 to 0.549 (+0.006). Feature is correct and fully tested (55/55 tests pass), but reverted due to factory internal eval detection gap. The factory eval could not detect the test suite (scored tests dimension at 0.5 "Not detected"), keeping composite below threshold despite actual code quality.

## What Changed
- Created `build_resampling_critic_prompt()` in `src/minimal_agora/agents.py` using inline prompt style (parameters, not file paths)
- Added `RESAMPLING_CRITIC` enum variant to `AgentRole` in `src/minimal_agora/models.py`
- Registered new role in `build_prompt()` dispatch function
- Added 11 unit tests for the new prompt builder in `tests/`
- PR #45 with 55 total passing tests, lint clean

## What We Learned
The factory's internal eval harness does not detect uv+pytest test suites — it scores tests and coverage at 0.5 ("Not detected") regardless of actual test pass rate. This is a metadata detection issue in the factory's eval.py, not a code quality problem. Both features implemented in this cycle are correct and production-ready; the revert is purely an artifact of eval detection gap.

## Links
- Issue: #40
- PR: #45

## Technical Notes
- Inline prompt migration is complete and matches the established pattern from PR #28 (actor/critic/judge already migrated)
- Resampling critic now integrates cleanly with particle filtering workflow
- All mypy errors in touched files remain but are pre-existing (not introduced by this change)
