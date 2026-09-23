# Progress Log

## Current Verified State

- Repository root: `/Users/ggiannon/Documents/gcg/minimal-harness/minimal-agora`
- Standard startup path: `./init.sh` (runs `uv sync`, `ruff check`, `pytest`)
- Standard verification path: `uv run pytest tests/ -v && uv run ruff check src/ tests/`
- All roadmap features through feat-012 passing; feat-004 validated with both API and Claude CLI providers
- Current blocker: None
- Test count: 416 tests, all green
- Lint: clean (ruff, 0 errors)
- Simulation validated: all 8 scenarios completed 50-step runs via RITS GLM-5.2; a fresh one-step intelligence run completed via authenticated Claude CLI on 2026-09-21
- Latest review: `docs/code-review-2026-09-23.md`; three runtime follow-ups remain

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

### Session 004

- Date: 2026-08-20 to 2026-08-21
- Goal: Finalize architecture, run simulations
- Completed:
  - LiteLLM provider + .env support + lazy client reuse (feat-009)
  - Conflict-gated resolution: 3-path loop (auto-merge / resolver / full review)
  - Role renames: CRITIC → CONSTRAINT_EVALUATOR, JUDGE → RESOLVER
  - Per-category plausibility scores (physical, consistency, pacing, rules)
  - Token optimization: max_tokens 4096→2048, conciser prompts
  - Narrative windowing enabled (default 20 steps)
  - Expanded actors: intelligence (4→6), complexity (4→5)
  - review_interval set per scenario (step_budget/100)
  - Run scripts: run-all.sh, run-single.sh, run-validate.sh
  - Validated all 8 scenarios (50-step runs via RITS GLM-5.2)
  - Removed .factory/ from git tracking
- Verification run: `uv run pytest tests/ -v` — 344 passed, `ruff check` — 0 errors
- Commits: 3427019, ae59431, afebe0f
- Open issues: #62 (parallel evaluator+resolver), #63 (Plotly viz), #64 (Three.js dashboard)

### Session 005

- Date: 2026-09-21
- Goal: Restore the baseline and implement adaptive step resolution (feat-010)
- Completed:
  - Repaired stale review-interval test isolation after the provider invocation refactor
  - Added opt-in `adaptive_steps` scenario configuration
  - Added deterministic numeric-delta extrapolation for routine steps
  - Forced full reasoning on first/final, wildcard, cadence, and state-drift inflection steps
  - Routed particle-filter execution through the shared step seam
  - Persisted per-step execution mode and trajectory-level skipped-call counts
  - Documented configuration, semantics, and approximation tradeoffs
- Verification run: `uv run pytest tests/ -q` — 398 passed; `uv run ruff check src/ tests/` — 0 errors
- Commits: a12f51c (baseline test fix); adaptive-step feature commit in this session
- Next priority: feat-011 (step batching)

### Session 006

- Date: 2026-09-21
- Goal: Implement multi-step LLM batching (feat-011)
- Completed:
  - Added opt-in `step_batching.batch_size` configuration
  - Added role-specific batch prompts and strict step-indexed response models
  - Preserved actor/evaluator/resolver debate with one provider call per role per batch
  - Applied and checkpointed each planned period sequentially
  - Preserved per-period termination and fitness/plateau checks
  - Conserved aggregate token counts by distributing batch-call usage across saved steps
  - Added deterministic fallback for missing or invalid batch resolutions
  - Rejected unsupported population, wildcard, resampling, and adaptive combinations explicitly
  - Documented scope, semantics, metrics, and tradeoffs
- Verification run: `uv run pytest tests/ -q` — 408 passed; `uv run ruff check src/ tests/` — 0 errors
- Next priority: feat-012 (state-in-prompt vs. file-based board)

### Session 007

- Date: 2026-09-21
- Goal: Implement configurable embedded versus file-based board access (feat-012)
- Completed:
  - Added `board_access: embedded|files`, preserving embedded prompts as the default
  - Centralized prompt-context selection and output parsing behind one board-access seam
  - Made provider workspace capability explicit and rejected incompatible providers early
  - Applied the same policy to flat and population loops
  - Kept stdout parsing with artifact fallback for embedded mode; made workspace artifacts authoritative in file mode
  - Rejected the unsupported file-mode plus step-batching combination during scenario validation
  - Raised the Claude subprocess turn cap to support workspace reads/writes and reject under-provisioned file-mode providers early
  - Documented configuration, provider compatibility, and behavior
  - Opened implementation issues #65 (feat-011) and #66 (feat-012)
  - Completed a fresh provider-backed intelligence simulation through authenticated Claude CLI: four proposals, one critique, one resolution, eight state-delta fields, and final step checkpoint 1
- Verification run: `uv run pytest tests/test_board_access.py -q` — 7 passed; `uv run pytest tests/ -q` — 415 passed; `uv run ruff check src/ tests/` — 0 errors
- External provider note: the configured RITS GLM-5.2 endpoint returned HTTP 503 during a separate 3-step attempt; the engine completed its failure path, then the Claude CLI validation succeeded
- Next priority: no unfinished roadmap features

### Session 008

- Date: 2026-09-23
- Goal: Review and organize the repository, add a compact architecture diagram
- Completed:
  - Fixed resampling workspace copies so overwritten parents are read from the original generation; added regression coverage for parent indices `[0, 0, 1]`
  - Consolidated duplicate development requirements and pytest configuration
  - Updated repository map, provider list, and README architecture diagram; removed the stale test-count badge
  - Recorded remaining review findings in `docs/code-review-2026-09-23.md`
- Verification: `./init.sh` completed with local cache access; 416 tests passed; Ruff check and format check passed
- Known risks: particle step history is not rebased after resampling; critics are invoked twice at resampling; checkpoint gap handling needs hardening. See the review note.
- Next priority: fix particle history lineage with an integration test, then remove the duplicate critic round

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
| feat-004 | core | End-to-end test with Claude CLI | passing |
| feat-005 | core | Fitness tracking (open_ended mode) | passing |
| feat-006 | reliability | Mode collapse mitigation | passing |
| feat-007 | reliability | Checkpoint and resume | passing |
| feat-008 | scenarios | Additional example scenarios | passing |
| feat-009 | core | Multi-provider LLM backend | passing |
| feat-010 | performance | Adaptive step resolution (skip LLM for routine steps) | passing |
| feat-011 | performance | Step batching (multi-step per LLM call) | passing |
| feat-012 | architecture | State-in-prompt vs. file-based board | passing |
