# Code Review — PR #45

**Reviewer:** code_reviewer agent
**Date:** 2026-08-18
**Commits reviewed:** e7f0ad0, 324b660 (narrative compression + visualization improvements)
**Baseline:** main

---

## Scope Summary

Two experiments reviewed:

1. **Narrative Compression (#29):** `compress_narrative()` in board.py, `narrative_window` in models.py, compression integration in loop.py, 11 tests.
2. **Visualization Improvements:** `plot_trajectory_comparison()`, `plot_wildcard_impact()`, `plot_agent_activity()` in visualize.py, `--types` CLI flag, 8 tests.

Also bundled: conditional wildcards (#34) and resampling critic (#40) from earlier commits.

---

## 7-Category Checklist

### 1. Correctness — PASS

**Narrative Compression:**
- `compress_narrative()` correctly parses `## Step N` headers with regex, preserves preamble and Step 0 (which has suffix " — Initial State" and thus doesn't match the `## Step (\d+)$` pattern — correct behavior).
- Re-compression preserves existing summary sections and extends them.
- `_extract_first_sentence()` handles both period-terminated and period-free text.
- Integration in `loop.py:171-176`: reads narrative from disk, compresses, writes back only if changed. The narrative file is guaranteed to exist at this point (created by `scenario.py:72` during workspace setup).
- `narrative_window` defaults to `None`, so compression is opt-in. Backward compatible.

**Visualization:**
- `plot_trajectory_comparison()` correctly uses `_get_nested()` for nested field access and handles multi-panel layout.
- `plot_agent_activity()` acceptance detection is a heuristic (key overlap between proposal and resolution delta) — reasonable approximation.
- `generate_all_plots()` type filtering via `_should()` helper is clean and correct.
- CLI `--types` uses argparse `choices=` for validation.

**One minor concern:** `ConditionOperator.EQ` uses `float(v) == t` (board.py:145). Float equality is fragile for non-integer values (e.g., 0.1+0.1+0.1 != 0.3). This is a known limitation, part of the conditional wildcards feature, and not a bug on the happy path.

No correctness bugs found on the happy path.

### 2. Security — PASS

- No user-controlled input flows into command execution, file path construction, or eval().
- No hardcoded secrets, API keys, or credentials.
- Matplotlib output paths are constructed from controlled `Path` objects.
- No injection vectors (SQL, XSS, command injection).
- All deserialization through Pydantic strict models with `extra="forbid"`.

### 3. Edge Cases — PASS

**Narrative Compression:**
- Empty narrative: returns unchanged (0 matches <= window). Tested: `test_empty_narrative`.
- Narrative at exactly window size: returns unchanged. Tested: `test_exactly_at_window_no_compression`.
- Window=1: compresses all but last step. Tested: `test_window_one`.
- Re-compression after adding steps: preserves old summary. Tested: `test_recompression_preserves_existing_summary`.
- No period in text: falls back to 100-char truncation. Tested: `test_first_sentence_extraction_no_period`.

**Visualization:**
- Empty trajectory list: all three functions return `output_path` without creating a figure. Tested for each.
- No proposals/critiques: `plot_agent_activity` renders "No agent activity data" placeholder. Tested: `test_plot_agent_activity_no_proposals`.
- Color overflow: `COLORS[t_idx % len(COLORS)]` handles >10 trajectories.

### 4. Missing Tests — PASS

**Narrative Compression:** 11 tests in `test_narrative_compression.py` covering:
- No-compression path, compression path, empty input, window=1, boundary (exactly at window), preamble preservation, re-compression, batch grouping, backward compatibility (None field), field-set, no-period text.

**Visualization:** 8 new tests in `test_visualize.py` covering:
- `plot_trajectory_comparison`: normal + empty input
- `plot_wildcard_impact`: normal + no events
- `plot_agent_activity`: normal + no proposals
- `generate_all_plots`: updated assertion (>=6 plots) + type filter test

All new public functions have corresponding tests. No untested error branches in the new code.

### 5. Style & Consistency — FAIL (minor)

**Issue: `_get_nested` duplicated in 3 files**
- `board.py:132` (new in this PR)
- `loop.py:424` (pre-existing)
- `visualize.py:474` (pre-existing)

The PR added a third copy in board.py for `evaluate_trigger_conditions()`. The function is identical in all three locations. This follows the pre-existing pattern but adds to the duplication.

**Severity: minor** — the duplication was pre-existing; the PR followed convention.

No dead code, no unused imports, no naming inconsistencies. Import organization is consistent.

### 6. Scope Compliance — PASS

**Issue #29 acceptance criteria:**

| Criterion | Status |
|-----------|--------|
| Sliding window (last N steps verbatim) | MET |
| Summarization of older narrative | MET (first-sentence extraction, batched per 10) |
| Tiered detail (3 tiers proposed) | SIMPLIFIED (2 tiers: summary + verbatim) |
| Configuration via scenario | MET (`narrative_window` field) |
| Keeps prompt size bounded | MET |
| No context window overflow on long runs | MET |

The implementation is simpler than the 3-tier proposal in the issue (no bullet-point intermediate tier, no `max_summary_tokens` cap, no `summary_interval` config). This is a reasonable simplification — first-sentence extraction avoids LLM summarization costs and the 2-tier approach still achieves the core goal of bounded prompt size.

**Visualization scope:** All three requested functions implemented (`plot_trajectory_comparison`, `plot_wildcard_impact`, `plot_agent_activity`), plus `--types` CLI flag and `generate_all_plots` integration. No scope creep beyond what was described in the PR.

**Spec fidelity: 5/6 criteria met** (tiered detail simplified from 3 tiers to 2).

### 7. Guardrail Compliance — PASS

| Guardrail | Status |
|-----------|--------|
| No file exceeds 500 lines | PASS (max: visualize.py at 481 lines) |
| All modified files within declared scope | PASS |
| No fixed_surfaces modified | PASS |
| No modifications to eval/score.py | PASS (eval/score.py is a new file from earlier commit, not modified) |
| No modifications to .factory/ contents | PASS (only .factory/reviews/ output) |
| No existing tests deleted or overwritten | PASS |
| No secrets or credentials | PASS |

---

## Issues Summary

| # | Severity | Category | File:Line | Description |
|---|----------|----------|-----------|-------------|
| 1 | minor | style | board.py:132, loop.py:424, visualize.py:474 | `_get_nested` duplicated in 3 files (pre-existing pattern, PR added 3rd copy) |
| 2 | minor | scope | board.py:150-202 | Narrative compression uses 2 tiers instead of 3 proposed in issue #29 (reasonable simplification) |
| 3 | minor | correctness | board.py:145 | Float equality in `ConditionOperator.EQ` is fragile for non-integer values (conditional wildcards feature, not narrative compression) |

---

## Plan Completion Status

| Deliverable | Status |
|-------------|--------|
| `compress_narrative()` in board.py | IMPLEMENTED (not stubbed) |
| `narrative_window` field in models.py | IMPLEMENTED (not stubbed) |
| Compression integration in loop.py `_run_step()` | IMPLEMENTED (not stubbed) |
| 11 narrative compression tests | IMPLEMENTED (not stubbed) |
| `plot_trajectory_comparison()` in visualize.py | IMPLEMENTED (not stubbed) |
| `plot_wildcard_impact()` in visualize.py | IMPLEMENTED (not stubbed) |
| `plot_agent_activity()` in visualize.py | IMPLEMENTED (not stubbed) |
| `--types` CLI flag | IMPLEMENTED (not stubbed) |
| 8 visualization tests | IMPLEMENTED (not stubbed) |

No stubs detected. All deliverables are fully implemented.

---

## Overall Result

**CLEAN**

- 0 critical issues
- 0 important issues
- 3 minor issues (all style/simplification, none blocking)
- Spec fidelity: 5/6 criteria met
- All deliverables implemented, no stubs
- All files within guardrail limits

**Decision: PROCEED to adversarial testing.**
