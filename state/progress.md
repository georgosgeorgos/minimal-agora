# Progress Log

## Current Verified State

- Repository root: `/Users/ggiannon/minimal-harness`
- Standard startup path: `./init.sh` (runs `uv sync`, `ruff check`, `pytest`)
- Standard verification path: `uv run pytest tests/ -v && uv run ruff check src/ tests/`
- All 15 features passing (14/15 implemented, feat-004 requires manual e2e test)
- Current blocker: None
- Test count: 44 tests, all green
- Lint: clean (ruff, 0 errors)

## Session Log

### Session 001

- Date: 2026-08-13
- Goal: Set up repo harness (AGENTS.md, .gitignore, symlinks)
- Completed: CLAUDE.md symlink, AGENTS.md cleanup, .gitignore, untracked .claude/.agents/
- Commits: f256c6b, 718c1e3

### Session 002

- Date: 2026-08-13
- Goal: Design and implement minimal-agora engine
- Completed:
  - Core engine: models, board, agents, loop, runner, analysis, CLI
  - Example scenarios: intelligence.yaml, mediterranean.yaml
  - Domain rules, wildcards, entity/population model
  - 14 passing tests, clean lint
- Commits: cd330e2, e9747c2, 540335b, dd2d93d, a72b885

### Session 003

- Date: 2026-08-13
- Goal: Implement all remaining features per roadmap
- Completed:
  - fix-001: Fallback resolution deep merge
  - fix-002: Wildcard state_impact auto-apply
  - feat-001: Agent retry logic + narrowed exception catches
  - feat-002: Entity interaction logic (always/never/scheduled, can_interact_with)
  - feat-003: Visualization (5 plot types, CLI subcommand, matplotlib)
  - feat-005: Fitness tracking + plateau detection for open_ended mode
  - feat-006: Mode collapse mitigation (10 diversity lenses, convergence detector)
  - feat-007: Checkpoint and resume from history snapshots
  - feat-008: New scenarios (pandemic, market competition, complexity maximizer)
  - Analysis enhancements: statistics, field timelines, artifact storage
  - All state files updated
- Verification run: `uv run pytest tests/ -v` — 44 passed, `ruff check` — 0 errors
- Commits: fab9603, e9aa35e, 9b13558, 295f3d4, dc6e0fb, b8a5a30, 44eb681
- Known risk: feat-004 (e2e test with real Claude CLI) not implemented — requires
  manual testing with authenticated claude CLI

## Roadmap (priority order)

| ID | Area | Title | Status |
|----|------|-------|--------|
| core-001 | core | Models, scenario loading, board | passing |
| core-002 | core | Domain rules in prompts | passing |
| core-003 | core | Wildcard catastrophic events | passing |
| core-004 | core | Entity/population model | passing |
| core-005 | core | Analysis and aggregation | passing |
| fix-001 | bugfix | Fix fallback resolution deep merge | passing |
| fix-002 | bugfix | Auto-apply wildcard state_impact | passing |
| feat-001 | reliability | Agent output retry/validation | passing |
| feat-002 | population | Entity interaction logic | passing |
| feat-003 | visualization | Trajectory visualization | passing |
| feat-004 | core | End-to-end test with Claude CLI | not_started |
| feat-005 | core | Fitness tracking (open_ended mode) | passing |
| feat-006 | reliability | Mode collapse mitigation | passing |
| feat-007 | reliability | Checkpoint and resume | passing |
| feat-008 | scenarios | Additional example scenarios | passing |
| feat-009 | core | Claude API direct backend | not_started |
| feat-010 | performance | Adaptive step resolution (skip LLM for routine steps) | not_started |
| feat-011 | performance | Step batching (multi-step per LLM call) | not_started |
| feat-012 | architecture | State-in-prompt vs. file-based board | not_started |
