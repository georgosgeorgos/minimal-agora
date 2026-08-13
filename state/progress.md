# Progress Log

## Current Verified State

- Repository root: `/Users/ggiannon/minimal-harness`
- Standard startup path: `./init.sh` (runs `uv sync`, `ruff check`, `pytest`)
- Standard verification path: `uv run pytest tests/ -v && uv run ruff check src/ tests/`
- Current highest-priority unfinished feature: fix-001 (fix _fallback_resolution deep merge)
- Current blocker: None

## Session Log

### Session 001

- Date: 2026-08-13
- Goal: Set up repo harness (AGENTS.md, .gitignore, symlinks)
- Completed: CLAUDE.md symlink, AGENTS.md cleanup, .gitignore, untracked .claude/.agents/
- Verification run: N/A (harness-only changes)
- Evidence captured: git commits
- Commits: f256c6b, 718c1e3
- Files or artifacts updated: AGENTS.md, CLAUDE.md, .gitignore
- Known risk or unresolved issue: None
- Next best step: Design worldsim architecture

### Session 002

- Date: 2026-08-13
- Goal: Design and implement worldsim engine
- Completed:
  - Core engine: models, board, agents, loop, runner, analysis, CLI
  - Example scenarios: intelligence.yaml (evolution), mediterranean.yaml (populations)
  - Domain rules system with applies_to filtering
  - Wildcard catastrophic events (6 types including alien/deus ex machina)
  - Entity/population model (population, force, critic, evaluator types)
  - Population mode with phased entity execution
  - CLI with mode/trajectory/step overrides
  - README documenting all modes and usage
  - 14 passing tests, clean ruff lint
  - Related projects reference list
- Verification run: `uv run pytest tests/ -v` — 14 passed, `ruff check` — 0 errors
- Evidence captured: Test output in session, commits on main
- Commits: cd330e2, e9747c2, 540335b, dd2d93d, a72b885
- Files or artifacts updated:
  - src/worldsim/*.py (8 modules)
  - scenarios/examples/intelligence.yaml, mediterranean.yaml
  - tests/test_models.py (14 tests)
  - pyproject.toml, uv.lock, README.md
  - All harness files updated to reflect worldsim specifics
- Known risk or unresolved issue:
  - _fallback_resolution uses dict.update() instead of deep merge (bug)
  - Wildcard state_impact is advisory only, not auto-applied
  - Entity interaction (can_interact_with) declared but not implemented
  - No e2e test with real Claude CLI subprocess
  - No visualization support yet
  - No fitness tracking for open_ended mode
- Next best step: Fix _fallback_resolution (fix-001), then auto-apply wildcard state_impact (fix-002)

## Roadmap (priority order)

| ID | Area | Title | Status | Effort |
|----|------|-------|--------|--------|
| core-001 | core | Models, scenario loading, board | passing | done |
| core-002 | core | Domain rules in prompts | passing | done |
| core-003 | core | Wildcard catastrophic events | passing | done |
| core-004 | core | Entity/population model | passing | done |
| core-005 | core | Analysis and aggregation | passing | done |
| fix-001 | bugfix | Fix fallback resolution deep merge | not_started | 5 min |
| fix-002 | bugfix | Auto-apply wildcard state_impact | not_started | 10 min |
| feat-001 | reliability | Agent output retry/validation | not_started | 30 min |
| feat-002 | population | Entity interaction logic | not_started | 1-2 hrs |
| feat-003 | visualization | Trajectory visualization | not_started | 1-2 hrs |
| feat-004 | core | End-to-end test with Claude CLI | not_started | 30 min |
| feat-005 | core | Fitness tracking (open_ended mode) | not_started | 1 hr |
| feat-006 | reliability | Mode collapse mitigation | not_started | 1 hr |
| feat-007 | reliability | Checkpoint and resume | not_started | 1 hr |
| feat-008 | scenarios | Additional example scenarios | not_started | 1 hr |
