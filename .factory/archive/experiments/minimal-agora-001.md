---
tags: [factory, experiment, minimal-agora]
project: minimal-agora
experiment_id: 1
verdict: revert
score_delta: +0.036
date: 2026-08-19
source: factory-archivist
---

# Experiment #1: Structured Logging Foundation

## Result
**REVERTED** — score improved from 0.543 to 0.579 (+0.036), but failed composite threshold (needed 0.6). Precheck gate: score improved but did not cross threshold, triggering auto-revert.

## What Changed
Added structlog foundation across core simulation modules:
- `loop.py`: instrumented main simulation loop with structured step logging
- `board.py`: added state change and snapshot logging
- `agents.py`: instrumented agent proposal and critique phases
- Replaced print statements with structured logs via `structlog.get_logger()` at module level

## Observability Impact
- Observability score: 0.237 → 0.654 (+0.417)
- Demonstrable improvement in logging infrastructure, but insufficient breadth to cross composite threshold

## What We Learned
Single improvements in one dimension, even substantial ones (+42% observability), do not guarantee threshold crossing. Composite scoring requires bundled improvements across multiple dimensions. Need to pair observability with complementary changes (coverage, tests, lint) in same experiment to achieve threshold lift.

## Anti-Patterns
- Single-dimension optimization unlikely to cross composite threshold
- Observability improvements must be paired with test/lint/type fixes for bundled effect

## Links
- PR: #61
- Cost: $3.79
