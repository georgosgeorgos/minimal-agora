---
tags: [factory, experiment, minimal-agora]
project: minimal-agora
experiment_id: 4
verdict: keep
score_delta: 0.018
date: 2026-08-19
source: factory-archivist
---

# Experiment #4: Proposal conflict detection + observability bundling

## Result
**KEEP** — score changed from 0.589 to 0.607 (+0.018)

Crossed composite threshold (0.6) naturally for first time in this cycle. Multi-dimension bundling strategy proved successful.

## What Changed
Two bundled improvements deployed in single atomic commit (2299f86):
1. **Proposal conflict detection**: Issue #41 resolved with explicit no-duplicate validation in proposal phase
2. **Observability instrumentation**: Extended structlog to core modules (board, agents, loop, runner)

Config state: 58 passing tests, lint clean (9/9), mypy clean (0 errors)

## Dimension Impact
- **observability**: +0.044 (0.733 → 0.777) — function coverage +46%, logging now in 9/10 core modules
- **capability_surface**: +0.009 (0.627 → 0.636) — entry points stabilized at 8/10, module count stable
- **composite**: +0.018 (0.589 → 0.607)

## What We Learned
Multi-dimension bundling (FIX + EXPLOIT in same PR) crosses composite threshold when single-dimension attempts fail. Proposal conflict detection was the fix; observability was the exploit. Combined, they exceeded the natural threshold without forcing --force flag. This validates the FEEC strategy (FIX → EXPLOIT → EXPLORE → COMPRESS).

## Links
- Issue: #41 (proposal duplicate detection)
- Commit: 2299f86
- Tests: 58 passing, full coverage of simulation core
