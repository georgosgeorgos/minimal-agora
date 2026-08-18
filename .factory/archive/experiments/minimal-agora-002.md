---
tags: [factory, experiment, minimal-agora]
project: minimal-agora
experiment_id: 002
verdict: revert
score_delta: +0.009
date: 2026-08-18
source: factory-archivist
---

# Experiment #002: Conditional wildcards — state-dependent triggers (Issue #34)

## Result
**REVERT** — score changed from 0.543 to 0.552 (+0.009). Feature is fully implemented and verified (85/85 tests pass, including 30 new tests for conditional wildcards). Code review and adversarial QA both PASS. Score.py composite shows 0.813 (above 0.60 threshold). Reverted due to factory internal eval detection gap: tests and coverage dimensions scored at 0.5 ("Not detected") despite 85 passing tests and full coverage.

## What Changed
- Added `ConditionOperator` enum (gt, lt, eq, gte, lte) in `src/minimal_agora/models.py`
- Added `TriggerCondition` model for state conditions (field, operator, threshold)
- Added `trigger_conditions` field to `WildcardEvent` (optional, default empty)
- Implemented `evaluate_trigger_conditions()` in `src/minimal_agora/board.py`
- Updated `_roll_wildcard()` to check conditions before firing (backward compatible)
- Added stdlib logging for condition checks (structlog upgrade deferred)
- 30 new unit tests for condition evaluation and boundary cases
- Updated pandemic.yaml scenario with conditional wildcard example
- All 85 tests pass, lint clean, no regressions

## What We Learned
1. Conditional wildcards dramatically increase simulation realism — state-dependent event triggering is a high-impact feature
2. The factory's internal eval cannot detect uv+pytest test suites or coverage metrics, scoring them at 0.5 "Not detected" regardless of actual test pass rate
3. Actual evaluation (score.py) correctly scores the implementation at 0.813 composite, well above threshold
4. Backward compatibility was maintained — existing scenarios without trigger_conditions work unchanged

## Links
- Issue: #34
- PR: #45

## Technical Notes
- Implementation matches hypothesis exactly: optional state conditions, enum-based operators, nested state field support
- 8 files changed, +374/-21 lines
- Code review found only non-blocking issues: duplicate _get_nested() helper (technical debt for future cleanup), stdlib logging instead of structlog (acceptable, can upgrade in next cycle)
- Adversarial test verified all 15 criteria: all operators work at boundaries, nested paths resolve correctly, backward compatibility across all 8 existing scenarios confirmed
- Boundary conditions tested: operators at exact threshold, operators with missing fields, nested path resolution through entities
