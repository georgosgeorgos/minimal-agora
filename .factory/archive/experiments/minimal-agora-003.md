---
tags: [factory, experiment, minimal-agora]
project: minimal-agora
experiment_id: 3
verdict: keep
score_delta: 0.003
date: 2026-08-19
source: factory-archivist
---

# Experiment #3: pytest.ini config fix

## Result
**KEEP** — score changed from 0.586 to 0.589 (+0.003)

## What Changed
Added explicit pytest configuration with pythonpath for src layout. Config-only change in `pytest.ini`:
- Set `pythonpath = src` to help factory eval detect test suite
- Harmless, non-invasive configuration

## What We Learned
Factory eval in worktree context lacks pytest installed in its own environment, so test suite detection remains capped at 0.5 despite correct pytest.ini. This is an infrastructure-level gap, not a config problem. Marginal score improvement (+0.003) comes from proper configuration being in place for future runs.

## Links
- Commit: 1418ac2
