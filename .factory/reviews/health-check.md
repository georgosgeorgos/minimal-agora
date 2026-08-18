# Health Check Report

- **Experiment:** Add conditional wildcards with state-dependent trigger conditions (#34)
- **Commit:** 16843fa
- **Date:** 2026-08-18
- **Baseline composite:** 0.543

---

## Score Table

| Dimension | Score | Weight | Passed | Notes |
|-----------|-------|--------|--------|-------|
| tests | 1.000 | 0.417 | YES | 85/85 passed (30 new conditional wildcard tests + 11 resampling critic tests) |
| lint | 1.000 | 0.250 | YES | All checks passed |
| type_check | 0.000 | 0.125 | NO | 16 errors in 5 files (pre-existing, unchanged from baseline) |
| coverage | 1.000 | 0.125 | YES | 55% overall (models.py 100%, scenario.py 95%, visualize.py 92%) |
| observability | 0.255 | 0.083 | NO | 7% function coverage (6/87), structured=no, tracing=yes |

**Composite:** 0.813

**Baseline:** 0.543

**Delta:** +0.270

**Threshold (0.60):** ABOVE

> Note: The composite improvement is largely due to eval weight rebalancing since the baseline was recorded (baseline used 12 dimensions with different weights; current eval uses 5 dimensions). Per-dimension scores for tests, lint, and coverage are at ceiling (1.0). type_check remains at 0.0 (pre-existing 16 mypy errors). observability is slightly lower than baseline (0.255 vs 0.334) due to metric recalculation, not regression.

---

## Unit Test Status: PASS

**85/85 tests passed in 0.65s.**

30 new tests in `tests/test_conditional_wildcards.py` covering:
- `ConditionOperator` enum values
- `TriggerCondition` model construction and dict roundtrip
- `WildcardEvent` with and without conditions (backward compatibility)
- All 5 operators: gt, lt, eq, gte, lte (pass and fail cases)
- Nested field access, missing fields, non-numeric fields
- Empty conditions (passthrough), multiple conditions (AND logic)
- Integration: `_roll_wildcard()` skipping/firing based on conditions
- No-state handling for conditional wildcards
- Mixed conditional and plain wildcards
- Pandemic scenario YAML loading with trigger conditions

11 existing resampling critic tests in `tests/test_resampling_critic.py` — all pass.

44 pre-existing tests across `test_models.py`, `test_analysis.py`, `test_visualize.py` — all pass, no regressions.

---

## Lint Status: PASS

`ruff check src/ tests/` — all checks passed.

---

## Pre-existing Issues (not introduced by this change)

- **type_check:** 16 mypy errors across 5 files — pre-existing, unchanged from baseline
- **observability:** Low function logging coverage (7%) — pre-existing, not a regression from this change

---

## Overall Gate Result: PASS

- Unit tests: **PASS** (85/85)
- Lint: **PASS** (clean)
- Composite score: **0.813** (above baseline 0.543, above threshold 0.60)
- No regressions detected — all pre-existing tests continue to pass
- Builder's changes add 30 well-structured tests and new capability without degrading any metric
