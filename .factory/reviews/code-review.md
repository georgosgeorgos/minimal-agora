# Code Review — H2: Conditional Wildcards (Issue #34)

- **Commit:** 16843fa (Add conditional wildcards with state-dependent trigger conditions)
- **Files changed:** 5 (models.py, board.py, loop.py, pandemic.yaml, test_conditional_wildcards.py)
- **Lines added:** 351, Lines removed: 4
- **Reviewer:** code_reviewer agent
- **Date:** 2026-08-18

---

## Files Changed (H2 scope)

| File | Change |
|------|--------|
| `src/minimal_agora/models.py` | +17 lines: `ConditionOperator` enum, `TriggerCondition` model, `trigger_conditions` field on `WildcardEvent` |
| `src/minimal_agora/board.py` | +57 lines: `_get_nested()`, `_CONDITION_OPS`, `evaluate_trigger_conditions()`, logging setup |
| `src/minimal_agora/loop.py` | +17/-4 lines: updated `_roll_wildcard()` signature and body, updated `run_trajectory()` call site |
| `scenarios/examples/pandemic.yaml` | +8 lines: `trigger_conditions` on two existing wildcards |
| `tests/test_conditional_wildcards.py` | +256 lines (new file): 30 unit tests |

---

## 7-Category Checklist

### 1. Correctness — PASS

- `evaluate_trigger_conditions()` at `board.py:150` correctly implements AND-logic: returns False on first failing condition, True only when all pass.
- `_get_nested()` at `board.py:131` correctly traverses dot-separated paths, returning None for missing keys or non-dict intermediates.
- `_CONDITION_OPS` dispatch table at `board.py:141` correctly maps all 5 operators to lambda comparisons.
- `_roll_wildcard()` at `loop.py:402` correctly skips conditional wildcards when state is None or conditions unmet, and falls through to probability roll when conditions are met.
- `run_trajectory()` at `loop.py:110` correctly reads current state before rolling wildcards, passing it to `_roll_wildcard`.
- Backward compatibility preserved: empty `trigger_conditions` list (the default) means the condition-check block is skipped entirely, retaining probability-only firing.
- No runtime crashes on the happy path.

### 2. Security — PASS

- No hardcoded secrets, API keys, or credentials.
- No injection vectors: field paths come from scenario YAML (developer-authored config), not untrusted user input.
- All deserialization through Pydantic strict models with `extra="forbid"`.
- `_get_nested()` only reads dict values; no code execution risk.
- No unsafe deserialization, path traversal, or command injection.

### 3. Edge Cases — PASS

- **Empty conditions list:** `evaluate_trigger_conditions([], state)` returns True — tested (`test_evaluate_empty_conditions_passes`).
- **Missing field:** returns None → function returns False — tested (`test_evaluate_missing_field_fails`).
- **Non-numeric field:** `isinstance` check rejects strings — tested (`test_evaluate_non_numeric_field_fails`).
- **State is None:** `_roll_wildcard` skips conditional wildcards — tested (`test_roll_wildcard_no_state_skips_conditional`).
- **Nested paths:** dot-separated traversal works for 2+ levels — tested (`test_evaluate_nested_field`).
- **Mixed events:** conditional wildcards skipped, plain wildcards still eligible — tested (`test_roll_wildcard_mixed_conditional_and_plain`).
- **Boundary values:** GT with equal value returns False — tested (`test_evaluate_gt_equal_fails`); GTE with equal value returns True — tested.

Minor untested edges (non-blocking):
- `bool` values pass `isinstance(v, (int, float))` since `bool` is a subclass of `int` in Python — `True` compares as `1`, `False` as `0`. Unlikely in practice but not tested.
- `ConditionOperator.EQ` uses `float(v) == t` at `board.py:144` which is susceptible to floating-point precision errors (e.g., `0.1 + 0.2 != 0.3`). Minor risk for user-specified thresholds with clean values.

### 4. Missing Tests — PASS

30 tests provide comprehensive coverage across all layers:

- **All 5 operators** tested with pass/fail/boundary cases (15 tests)
- **Nested field access**, missing field, non-numeric field (3 tests)
- **Empty conditions**, multiple conditions AND logic (2 tests)
- **Model construction**, validation from dict, serialization roundtrip (4 tests)
- **`_roll_wildcard` integration**: conditions not met, conditions met, backward compat, no state, mixed events (5 tests)
- **Pandemic YAML** scenario loading with conditions (1 test verifying all 3 wildcards parse correctly)

No critical test gaps. The bool-as-numeric and float-equality edges noted in category 3 are not tested but are minor.

### 5. Style & Consistency — PASS (with notes)

- **Naming:** snake_case throughout, consistent with project conventions.
- **Import organization:** clean, alphabetized.
- **Model style:** follows existing Pydantic patterns (`ConfigDict(extra="forbid")`, `Field(default_factory=list)`).
- **Logging:** uses `logging.getLogger(__name__)` — consistent with existing `loop.py` pattern.
- **No dead code:** no unused imports or unreachable branches.

Issues noted:
- **Code duplication (important):** `_get_nested()` is duplicated identically in `board.py:131` and `loop.py:417`. The `loop.py` version predates this PR and is used by `_check_termination()` and `_classify_outcome()`. The new `board.py` version duplicates it for `evaluate_trigger_conditions()`. Should be consolidated to one canonical location and imported.
- **Strategy divergence (minor):** The H2 strategy specified "Bundle: add structlog to board.py wildcard evaluation for observability" but stdlib `logging` was used. This is consistent with the rest of the codebase (`loop.py`, `agents.py` all use stdlib logging), so the divergence is reasonable.

### 6. Scope Compliance — PASS

**Spec fidelity: 5/6 criteria met.**

| # | Criterion (from issue #34) | Status | Evidence |
|---|---|---|---|
| 1 | State-based trigger conditions on wildcards | ✅ MET | `models.py:105-111`, `board.py:150-172` |
| 2 | All conditions must be true (AND logic) | ✅ MET | `board.py:151` for-loop with early return False |
| 3 | Comparison operators | ✅ MET | `ConditionOperator` enum: gt, lt, eq, gte, lte |
| 4 | Backward compatible (existing wildcards unchanged) | ✅ MET | `trigger_conditions` defaults to empty list |
| 5 | Example scenario demonstrates conditional wildcards | ✅ MET | `pandemic.yaml:129-132`, `pandemic.yaml:151-154` |
| 6 | `probability_modifier` (scale probability by state value) | ❌ NOT IMPLEMENTED | Justified: strategy document scoped H2 to trigger conditions only |

The `probability_modifier` omission is justified by the strategy document, which explicitly scoped H2 to the trigger-condition gating mechanism. No unjustified scope shrinkage.

**No scope creep:** The `RESAMPLING_CRITIC` enum addition is in the separate H1 commit (2d5e6db), correctly separated. No unrelated changes in the H2 commit.

### 7. Guardrail Compliance — PASS

| Guardrail | Status | Evidence |
|-----------|--------|---------|
| No file exceeds 500 lines | ✅ | models.py: 223, board.py: 172, loop.py: 447, tests: 256 |
| All modified files within declared scope | ✅ | `src/minimal_agora/**`, `tests/**`, `scenarios/**` per config |
| No fixed_surfaces modified | ✅ | `fixed_surfaces` is empty in config |
| No modifications to eval/score.py | ✅ | Not touched by H2 commit |
| No .factory/ contents modified | ✅ | Not touched by H2 commit |
| No existing tests deleted or overwritten | ✅ | New test file; no existing tests touched |
| No secrets or credentials | ✅ | No sensitive data in any changed file |

---

## Issues Summary

| # | Severity | Category | File:Line | Description |
|---|---|---|---|---|
| 1 | important | style | `board.py:131`, `loop.py:417` | `_get_nested()` duplicated identically in both files. Should be consolidated to one canonical import. |
| 2 | minor | edge-cases | `board.py:144` | `EQ` operator uses `float(v) == t` — susceptible to floating-point precision errors. Consider `math.isclose()`. |
| 3 | minor | edge-cases | `board.py:153` | `isinstance(value, (int, float))` passes for `bool` values (Python subclass of `int`). Could cause surprising 0/1 comparisons. |
| 4 | minor | style | `board.py:17` | Strategy specified structlog but stdlib logging used. Consistent with codebase; diverges from stated plan. |
| 5 | minor | scope | — | `probability_modifier` from issue #34 not implemented. Justified by strategy scoping. |

No critical issues found. No stubs detected — all functions contain real implementations.

---

## Plan Completion

| Deliverable | Status |
|---|---|
| `ConditionOperator` enum in models.py | ✅ Implemented (5 operators) |
| `TriggerCondition` model in models.py | ✅ Implemented (field, operator, threshold) |
| `trigger_conditions` field on `WildcardEvent` | ✅ Implemented (optional, empty default) |
| `evaluate_trigger_conditions()` in board.py | ✅ Implemented with logging |
| Updated `_roll_wildcard()` in loop.py | ✅ Conditions checked before probability roll |
| Updated pandemic.yaml with examples | ✅ Two conditional wildcards added |
| 30 unit tests | ✅ All passing |

No stubbed deliverables. All implementations are complete with real logic.

---

## Overall Result

**ISSUES_FOUND** — No critical issues. One important style issue (code duplication) and four minor issues. All 7 categories evaluated and pass.

**Spec fidelity:** 5/6 criteria met (probability_modifier justified as out of strategy scope).

**Gate decision:** ✅ **PROCEED** to adversarial testing.
