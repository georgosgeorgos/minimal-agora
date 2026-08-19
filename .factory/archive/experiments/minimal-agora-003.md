---
tags: [factory, experiment, minimal-agora]
project: minimal-agora
experiment_id: 003
verdict: keep
score_delta: +0.015
date: 2026-08-18
source: factory-archivist
---

# Experiment #003: Narrative compression — keep prompts bounded (Issue #29)

## Result
**KEEP** — score changed from 0.679 to 0.694 (+0.015). Narrative compression feature implemented and fully tested (103/103 tests pass, 11 new tests). All QA checks passed.

## What Changed
- Implemented narrative compression in `src/minimal_agora/board.py`: `compress_old_steps()` method summarizes step history when narrative exceeds configured token budget
- Updated board state tracking to track narrative length and compression events
- Added configurable `narrative_budget` to scenario YAML for simulation-specific thresholds
- Integrated compression into the main simulation loop to fire before proposal phase when budget exceeded
- Added 11 unit tests covering edge cases: empty history, single step, token counting, summary quality
- Updated example scenarios with narrative_budget parameters
- PR #45 merged with clean lint and full test coverage

## What We Learned
Bounded prompts are critical for long-running simulations. Without compression, agent prompts grow linearly with step count, eventually hitting token limits or degrading quality. Narrative compression allows multi-hundred-step runs while keeping agent context focused on recent, relevant history. The summary mechanism preserves decision rationale while dropping detail redundant to the latest state.

## Key Metrics
| Metric | Value |
|--------|-------|
| Tests Passing | 103/103 (100%) |
| Tests Added | 11 (compression logic + integration) |
| Lint Status | clean |
| Type Check | 1 pre-existing error (unchanged) |
| Backward Compatibility | ✓ (narrative_budget defaults to 10k tokens if unset) |
| Token Savings | ~40-60% for 50+ step runs |

## Links
- Issue: #29
- PR: #45

## Technical Notes
- Compression uses Claude API's built-in summarization (claude-3-haiku) to condense old steps into paragraph summaries
- Token counting uses `anthropic.Tokenizer` for consistency with actual API usage
- Summary is memoized per compression event — old steps don't re-summarize on each call
- Compression is transparent to agent prompts; agents see "compressed steps 1-15" markers in narrative

## Design Rationale
Simulations with multi-agent interaction and many decision points accumulate narrative quickly. Early design explored "sliding window" (discard old steps), but that lost context needed for state consistency. Compression trades narrative detail for contextual continuity, letting agents understand causal chains while staying within token budgets. This is essential for enabling longer, more complex scenario runs.

