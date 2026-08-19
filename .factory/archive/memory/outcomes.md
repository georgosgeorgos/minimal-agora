
============================================================
  Results for: "experiment verdict keep revert"
  Wing: project:/Users/ggiannon/Documents/gcg/minimal-harness/minimal-agora/.factory-worktrees/run-28324432
  Room: experiments
============================================================

  [1] project:/Users/ggiannon/Documents/gcg/minimal-harness/minimal-agora/.factory-worktrees/run-28324432 / experiments
      Source: current.md
      Match:  cosine_sim=0.216  bm25=0.288

      ## Strategy — 2026-08-19
      
      ### Design Space
      | Dimension | Score | Notes |
      |---|---|---|
      | Features | 3 | 14/15 features built; 10 open enhancement issues remain |
      | Bug fixes | 4 | Eval harness fixed, lint fixed; no open bugs |
      | Instrumentation | 1 | 14% function coverage, no structured logging, 3 files uninstrumented |
      | Flow changes | 3 | Core loop, population mode, entity stepping all implemented |
      | New agents | 2 | Actor/critic/judge/evaluator roles exist; no new agent types recently |
      | Prompt engineering | 2 | Diversity lenses added; no recent prompt tuning |
      | Eval improvements | 3 | 5 eval dimensions configured; eval harness recently fixed |
      | Knowledge management | 1 | No vault notes, no SPEC.md, no prior experiment data |
      | Infrastructure | 3 | Factory initialized, eval working, CI not yet configured |
      | Operational execution | 1 | No end-to-end benchmark runs recorded |
      | Self-evolution | 0 | First factory cycle — no prior experiments |
      
      **Underserved:** Instrumentation (1), Knowledge management (1), Operational execution (1)
      
      ### Observations
      - Current composite score: 0.812 (raw weighted), ~0.543 (factory composite with growth weighting)
      - Weakest eval dimension: type_check (0.0) — 16 mypy errors across 5 files
      - Second weakest: observability (0.237) — 4/84 functions instrumented, no structured logging
      - Strong dimensions: tests (1.0), lint (1.0), coverage (1.0)
      - Last 3 experiments: none — this is the first factory cycle
      - Pattern: Hygiene is mostly green (3/4 passing) but type_check at 0.0 drags composite below threshold. Growth dimensions (observability, capability_surface) are the primary bottleneck for reaching 0.6.
      - The research report recommends implementing observability foundation FIRST, then layering capability features on top — structlog enables structured logging for all future instrumentation.
      - Issue #41 (conflict detection) is the highest impact/effort ratio among the 10 open issues — low complexity, prevents silent state corruption in multi-actor scenarios.
      
      ### Hypotheses
      
      #### H1: Add structlog foundation and instrument core simulation modules
      - **Category:** EXPLORE
      - **New:** yes
      - **Growth dimension:** observability
      - **What:** Add `structlog` dependency to `pyproject.toml`. Create `src/minimal_agora/logging.py` with auto-detecting configuration (ConsoleRenderer for TTY, JSONRenderer for production). Add `get_logger()` helper with trajectory_id binding. Instrument the three uninstrumented high-priority modules:
        - `src/minimal_agora/loop.py` — replace 8 print statements with structured logs at step boundaries (step start/end, proposal count, critic scores, judge decisions)
        - `src/minimal_agora/board.py` — log state reads/writes, snapshot creation, resolution application (18 functions, currently 0 log statements)
        - `src/minimal_agora/agents.py` — log agent invocations with role, timeout, retry count, and parse failures
        - Add test for logging configuration in `tests/test_logging.py`
      - **Files to modify:** `pyproject.toml`, `src/minimal_agora/logging.py` (new), `src/minimal_agora/loop.py`, `src/minimal_agora/board.py`, `src/minimal_agora/agents.py`, `tests/test_logging.py` (new)
      - **Estimated LOC:** ~150 lines (logging module ~40, instrumentation ~80, test ~30)
      - **Why:** Observability is at 0.237 — the weakest growth dimension. The eval measures function coverage (currently 4/84 = 5%), structured logging (currently no), and log density. Adding structlog with instrumentation across the 3 uninstrumented core modules should raise function coverage to ~35/84 (42%) and enable structured JSON output. The research report identifies this as the foundational layer that all future instrumentation builds on. Per AgentTrace framework patterns, the three instrumentation surfaces (operational, cognitive, contextual) map directly to loop.py, agents.py, and board.py.
      - **Expected impact:** observability 0.237 → 0.65+ (structured=yes, coverage 5%→42%, density improvement). Composite +0.034 from observability weight alone, plus growth dimension boost.
      - **Priority:** high
      
      #### H2: Implement proposal conflict detection before judge resolution (issue #41)
      - **Category:** EXPLORE
      - **New:** yes
      - **Growth dimension:** capability_surface
      - **Addresses:** #41
      - **What:** Add a `Conflict` dataclass to `src/minimal_agora/models.py` with fields: `field` (contested state key), `sources` (list of agent name + proposed value pairs). Add `detect_conflicts(proposals: list[Proposal]) -> list[Conflict]` function to `src/minimal_agora/agents.py` that identifies proposals targeting the same state fields. Integrate into `src/minimal_agora/loop.py` at the judge resolution step: before calling the judge, detect conflicts and inject a structured conflict summary into the judge prompt so contested fields are highlighted. Add tests in `tests/test_conflict_detection.py` covering: no conflicts, single conflict, multi-field conflicts, nested state key conflicts.
      - **Files to modify:** `src/minimal_agora/models.py`, `src/minimal_agora/agents.py`, `src/minimal_agora/loop.py`, `tests/test_conflict_detection.py` (new)
      - **Estimated LOC:** ~80 lines (Conflict model ~15, detect_conflicts ~25, loop integration ~15, tests ~25)
      - **Why:** With 5+ actors, the judge receives a flat list of proposals and must manually spot field overlaps — easy to miss, leading to silent state corruption. The research report ranks #41 as the highest impact/effort issue: low complexity, immediate quality improvement, no architectural changes required. The `defaultdict(list)` approach for field grouping is straightforward and well-understood.
      - **Expected impact:** capability_surface +0.1 (new user-facing feature addressing an open issue). Indirect quality improvement: judge decisions become more accurate when conflicts are explicitly highlighted, reducing state corruption in population mode simulations.
      - **Priority:** high
      
      ### Anti-patterns to Avoid
      - **Don't fix type_check by adding `# type: ignore` comments** — the 16 mypy errors are real type issues (union narrowing, list covariance, missing stubs). Proper fixes require isinstance guards, Sequence annotations, and types-PyYAML. Suppressing errors provides no real improvement.
      - **Don't attempt provider abstraction (#39, #44, #33) in a single PR** — research report identifies these as multi-PR architectural changes with cross-cutting dependencies. Each requires a new interface, multiple backend implementations, and config schema changes.
      - **Don't instrument all 84 functions at once** — prioritize the core simulation flow (loop, board, agents) first. Analysis, runner, and scenario modules can be instrumented in a follow-up cycle.
      - **Don't add features without tests** — factory.md constraints require each change to include at least one test.
      
      ### New Backlog Items
      - Fix 16 mypy type errors to raise type_check from 0.0 to 1.0 (largest single-dimension impact on composite: +0.125). Quick wins: add `types-PyYAML` dep, fix union narrowing in `runner.py`, add type annotation in `dashboard.py`. Medium: fix Step vs int in `visualize.py`, list covariance issues.
      - Instrument remaining modules (analysis.py, runner.py, scenario.py) with structlog to push observability coverage from ~42% to 60%+.
      - Agent calibration tracking (#35): track per-agent acceptance rates by comparing proposals to judge resolutions. Data-driven scenario refinement.

  --------------------------------------------------------

