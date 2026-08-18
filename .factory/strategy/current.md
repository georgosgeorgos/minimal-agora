## Strategy — 2026-08-18

### Observations
- Current composite score (factory eval): 0.552
- Current composite score (score.py): 0.813
- Weakest factory eval dimensions: tests (0.5, "Not detected"), coverage (0.5, "Not detected"), research_grounding (0.0)
- Last 2 experiments: exp-1 reverted (precheck), exp-2 reverted (precheck) — both QA-passed
- Pattern: Factory internal eval does not detect uv+pytest test suites, capping composite below 0.60

### Blocking Issue
The factory's internal eval `tests` and `coverage` dimensions report "Not detected" despite 85 passing tests and 53% coverage. These two dimensions (combined weight 0.28) are stuck at 0.5, dragging the composite below 0.60 threshold. The custom eval harness (score.py) correctly detects everything and scores 0.813.

**Resolution needed:** Either fix factory detection (may need project config changes) or adjust the evaluation pipeline to use score.py output.

### Completed Work (code still in tree)
- **H1 (Bug #40):** build_resampling_critic_prompt() in agents.py, RESAMPLING_CRITIC enum, 11 tests
- **H2 (Issue #34):** Conditional wildcards — ConditionOperator, TriggerCondition, evaluate_trigger_conditions(), 30 tests
- **Eval harness:** eval/score.py with 5 dimensions, factory.md, .factory/ initialized

### Backlog
- State schema validation (#36)
- Narrative compression (#29)
- Structured logging (structlog) across uninstrumented files
- ESS-based resampling (#32)
- Fix factory test/coverage detection issue (PRIORITY — blocks all future experiments)

### Anti-patterns to Avoid
- Factory internal eval does not detect uv+pytest — score.py is the accurate measure
- All experiments will be reverted by precheck until the detection issue is resolved

### Session State
- **Mode:** Improve
- **Current phase:** Cycle complete (archival)
- **Active experiments:** None (both reverted by precheck)
- **Next action:** Fix factory test/coverage detection issue, then re-run experiments
