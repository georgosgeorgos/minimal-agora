# Research Report — minimal-agora

## Project Summary

minimal-agora is an LLM-powered world simulation engine for exploring counterfactual hypotheses through Monte Carlo methods. It uses adversarial multi-agent debate (propose→critique→resolve) across N trajectories with particle filtering to focus compute on interesting branches. Current baseline score: **0.543/0.60** (needs +0.057). 16 open GitHub issues focused on simulation improvements, agent enhancements, and performance.

**Current State:**
- Tests: 1.0 (44 passing)
- Lint: 1.0 (clean)
- Type checking: **0.0** (16 mypy errors in 5 files) ← weakest
- Coverage: 1.0 (53%)
- Observability: **0.237** (14% function logging, no structured logging) ← second weakest

**User Goals:** Implement open issues, improve simulation quality/speed, improve visualizations.

---

## External Research Findings

### 1. Type Safety in Python with Pydantic + Mypy

The current type_check dimension failure (16 errors) is the single biggest drag on the composite score. Research shows Pydantic v2 with mypy requires explicit plugin configuration.

**Key Fix:** Enable `pydantic.mypy` plugin in pyproject.toml:
```toml
[tool.mypy]
plugins = ["pydantic.mypy"]
follow_imports = "silent"
warn_redundant_casts = true
warn_unused_ignores = true
disallow_any_generics = true
no_implicit_reexport = true

[tool.pydantic-mypy]
init_typed = true
init_forbid_extra = true
warn_required_dynamic_aliases = true
```

**Specific Errors to Fix:**
- `scenario.py:7` - Missing type stubs for `yaml` → install `types-PyYAML`
- `analysis.py:126`, `runner.py:37`, `visualize.py:101-157` - Type narrowing issues (Union types, list variance)
- `dashboard.py:106,124,579-582` - Missing type annotations, partial object attribute access

**Expected Impact:** Fixing all 16 errors → type_check: 0.0 → 1.0 (weight 0.125) = **+0.125 to composite score** (reaches 0.668, exceeds 0.60 threshold).

**Source:** [Pydantic Mypy Integration Docs](https://pydantic.dev/docs/validation/latest/integrations/dev-tools/mypy/)

### 2. Structured Logging for Observability

Current observability score (0.237) reflects 14% function logging coverage with no structured logging. Modern Python observability (2026) uses `structlog` with JSON output and OpenTelemetry correlation.

**Best Practices:**
1. **Use structlog with JSONRenderer** for machine-parseable logs
2. **Add correlation IDs** - trajectory_id and step number in every log line
3. **Log events, not sentences** - use past-tense verbs: `step_completed`, `wildcard_fired`, `proposal_rejected`
4. **Target uninstrumented files first**:
   - `board.py` (18 functions, 0 logs) - state mutations, wildcard rolls, checkpointing
   - `analysis.py` (9 functions, 0 logs) - outcome classification, aggregation
   - `scenario.py` (6 functions, 0 logs) - scenario loading, workspace setup
5. **Appropriate log levels**:
   - ERROR: Agent failures, validation errors
   - WARN: Retries, timeout warnings
   - INFO: Step start/end, trajectory completion, outcome classification
   - DEBUG: Detailed proposals, state deltas

**Practical Pattern for Simulation Engines:**
```python
import structlog
logger = structlog.get_logger()

# Bind trajectory context once at trajectory start
logger = logger.bind(trajectory_id=traj_id, scenario=scenario.name)

# Log events with structured fields
logger.info("step_started", step=3, review_step=True)
logger.info("wildcard_fired", wildcard="asteroid_impact", probability=0.02)
logger.info("proposal_accepted", actor="natural_selection", plausibility=0.87)
logger.info("step_completed", step=3, duration_ms=1243, state_changed=True)
```

**Expected Impact:** Adding structured logging to 33 uninstrumented functions → observability: 0.237 → ~0.75 = **+0.043 to composite score**.

**Sources:**
- [Structured Logging Best Practices 2026](https://www.grepr.ai/blog/structured-logging-best-practices)
- [Python Logging Best Practices with structlog](https://tutorials.technology/tutorials/python-logging-best-practices-structlog-loguru-2026.html)

### 3. Sequential Monte Carlo / Particle Filtering

The project already implements particle filtering (resampling trajectories), but issue #32 proposes using **Effective Sample Size (ESS)** instead of fixed intervals.

**ESS Threshold Method:**
```
ESS = 1 / sum(w_i^2)
```
- If all weights equal → ESS = N (diversity is high, no resampling needed)
- If one trajectory dominates → ESS ≈ 1 (degeneracy, must resample)

**Standard Practice:** Resample when `ESS < N/2`.

**Implementation Pattern from `particles` library:**
```python
def compute_ess(weights):
    return 1.0 / np.sum(weights ** 2)

# In runner loop:
if compute_ess(normalized_weights) < len(trajectories) / 2:
    resample()
```

**Benefit:** Avoids unnecessary resampling when diversity is high, resamples aggressively when one trajectory dominates. More principled than fixed intervals.

**Source:** [particles: Sequential Monte Carlo in Python](https://github.com/nchopin/particles)

### 4. Multi-Agent Debate Systems Research

Recent controlled study on LLM multi-agent debate for logical reasoning reveals critical findings relevant to minimal-agora's propose→critique→resolve loop:

**Key Findings:**
1. **Intrinsic reasoning strength dominates** - Performance is "bounded by the strongest participant." Weak agents can't be fixed by better debate structure.
2. **Diversity helps moderately** - Heterogeneous teams (mixing strong/weak) show "modest but consistent gains" when at least one strong reasoner is present.
3. **Process quality over structure** - Effective debates require:
   - Inclusive deliberation (agents respond to each other, not speak past)
   - Evidence-based reasoning (changes correlate with argument validity)
   - Genuine improvement (correcting errors, not just aggregating guesses)
4. **Majority pressure is a failure mode** - Weak agents correct themselves only 3.6% of the time when facing incorrect majorities.
5. **Correcting wrong consensus matters most** - Ability to overturn incorrect group beliefs is the hallmark of effective debate.

**Implications for minimal-agora:**
- **Issue #44 (temperature scheduling)** aligns with research - exploratory early (diversity), conservative late (consolidation)
- **Issue #35 (calibration tracking)** enables detecting "persuasiveness over accuracy" failure modes
- **Issue #41 (conflict detection)** helps judge identify when proposals contradict (forces genuine deliberation)
- Current architecture is sound: multiple critics + judge aggregation matches "heterogeneous teams with strong reasoners" pattern

**Source:** [Can LLM Agents Really Debate? A Controlled Study](https://arxiv.org/html/2511.07784v1)

### 5. Adaptive Time Stepping in Simulation Engines

Issue #42 (multi-resolution stepping) proposes coarse steps for boring periods, fine-grained steps at critical moments. This is a standard technique in computational physics.

**Key Concepts:**
- **Local error estimation** - Monitor how much state changes per step
- **Dynamic step size adjustment** - Increase Δt when solution is smooth, decrease when rapid changes occur
- **Multi-scale systems** - Different regions/entities can use different time scales simultaneously

**For LLM simulation engines:**
Instead of traditional error estimation (not available without ground truth), use:
- **State change magnitude** - Compare state before/after, measure Δ (issue #30 proposes this for review intervals)
- **Wildcard events** - Force fine-grained stepping when wildcard fires
- **Fitness gradient** - In open_ended mode, use fitness change rate as proxy for "interestingness"

**Practical Pattern:**
```python
# Start with coarse steps (100M years)
base_step_size = 100_000_000

# Adjust based on state change
if state_change_magnitude > HIGH_THRESHOLD:
    step_size = base_step_size / 10  # Fine-grained
elif wildcard_just_fired:
    step_size = base_step_size / 5   # Medium resolution
else:
    step_size = base_step_size       # Coarse
```

**Benefit:** 10-50x reduction in LLM calls for long simulations without losing accuracy at inflection points.

**Source:** [Adaptive Time-Stepping Methods](https://www.emergentmind.com/topics/adaptive-time-stepping-methods)

---

## Prior Knowledge (Archive)

No archive sources available - this is a new project in the factory system.

---

## Recommended Focus Areas

### Tier 1: Quick Wins for Eval Score (reach 0.60)

#### 1.1 Fix Type Checking Dimension (HIGHEST PRIORITY)
**Impact:** +0.125 to composite score (0.543 → 0.668)  
**Effort:** Low (configuration + 16 targeted fixes)  
**Actions:**
- Add `pydantic.mypy` plugin to pyproject.toml with strict settings
- Install `types-PyYAML` dev dependency
- Fix 16 specific mypy errors:
  - `analysis.py:126` - Type narrow before `.append()`
  - `scenario.py:7` - Add type stubs
  - `dashboard.py:106,124,579-582` - Add type annotations, fix partial access
  - `runner.py:37-38` - Type narrow Union return before use
  - `visualize.py:101-157` - Fix type mismatches (int vs Step, list invariance)

**References:** Mypy errors are in files handling core simulation data structures - high confidence that fixes won't break tests.

#### 1.2 Improve Observability (MEDIUM PRIORITY)
**Impact:** +0.043 to composite score (from 0.237 → ~0.75 on observability dimension)  
**Effort:** Medium (add structlog, instrument 33 functions across 3 files)  
**Actions:**
- Add `structlog` dependency
- Configure JSONRenderer in CLI entry point
- Instrument the 3 uninstrumented files with correlation IDs:
  - `board.py` - state_loaded, state_saved, wildcard_fired, checkpoint_created
  - `analysis.py` - outcome_classified, statistics_computed, report_generated
  - `scenario.py` - scenario_loaded, workspace_setup_complete
- Bind trajectory_id and scenario name at trajectory start
- Use event-based logging (past-tense verbs, structured fields)

**Expected Total from Tier 1:** 0.543 + 0.125 + 0.043 = **0.711** (exceeds 0.60 threshold by healthy margin)

---

### Tier 2: High-Impact Simulation Improvements (aligned with user goals)

#### 2.1 State Schema Validation (Issue #36)
**Impact:** Correctness - prevents invalid state_deltas from corrupting state  
**Effort:** Medium  
**Why:** Research shows type safety prevents entire classes of bugs. Pydantic already used for scenario models - extend to runtime state validation.  
**Actions:**
- Define optional `state_schema` field in Scenario config (Pydantic model)
- Validate state_delta against schema before deep merge in `board.apply_resolution()`
- Emit structured log + continue with rejected delta (don't crash entire trajectory)

**Alignment:** Directly addresses quality and reliability.

#### 2.2 Narrative Compression (Issue #29)
**Impact:** Enables long simulations (500+ steps) without prompt bloat  
**Effort:** Medium-High  
**Why:** Current inline prompts embed full narrative - grows unbounded. Research on adaptive methods suggests compress old steps, keep recent ones.  
**Actions:**
- Summarize narrative segments older than K steps (e.g., K=20)
- Keep last K steps verbatim for recency
- Add summary_length field to track compression ratio
- Test with 100-step simulation to verify trajectory quality maintained

**Alignment:** Critical for "make simulation better/faster" goal.

#### 2.3 Resampling Critic Bug Fix (Issue #40)
**Impact:** Correctness - the only open bug  
**Effort:** Low  
**Why:** All other prompts were migrated to inline style in PR #28, this one was missed.  
**Actions:**
- Migrate `build_resampling_critic_prompt()` from file-based to inline (pass state, narrative, trajectory list in prompt)
- Test with particle filtering scenario

**Alignment:** Bug fix, should be prioritized.

#### 2.4 Agent Temperature Scheduling (Issue #44)
**Impact:** Better exploration/exploitation tradeoff  
**Effort:** Low-Medium  
**Why:** Multi-agent debate research shows diversity helps in early stages, convergence helps late. Temperature is the natural knob.  
**Actions:**
- Add `temperature_schedule` config: `{initial: 1.0, final: 0.3, decay: "linear"}`
- Pass temperature to provider based on `step / max_steps` ratio
- Test with intelligence scenario (500 steps) - measure outcome diversity vs baseline

**Alignment:** Directly improves simulation quality via better agent reasoning.

---

### Tier 3: Performance Improvements (longer-term)

#### 3.1 ESS-Based Resampling (Issue #32)
**Impact:** Smarter resampling - avoid unnecessary resampling, trigger when degeneracy occurs  
**Effort:** Low  
**Why:** Standard practice in particle filtering literature. Fixed intervals are inefficient.  
**Actions:**
- Implement `compute_ess(weights)` function
- Replace `if step % interval == 0` with `if ess < len(trajectories) / 2`
- Log ESS value at each review step for observability

#### 3.2 Adaptive Review Interval (Issue #30)
**Impact:** Skip critic/judge on boring steps - 2-5x fewer LLM calls  
**Effort:** Medium  
**Why:** Research on adaptive time stepping shows state change magnitude is reliable proxy for "needs scrutiny."  
**Actions:**
- Compute state change magnitude: `json_diff(state_before, state_after)`
- If magnitude < threshold and no wildcard → skip review, use _fallback_resolution
- If magnitude > threshold → force review (set next_review_step = current_step)

#### 3.3 Multi-Resolution Stepping (Issue #42)
**Impact:** 10-50x reduction in steps for long timescale simulations  
**Effort:** High  
**Why:** 3 billion years of unicellular life doesn't need 300 LLM calls. Adaptive time stepping is standard in computational physics.  
**Actions:**
- Add `step_scale_range` to scenario: `{min: 1_000_000, max: 100_000_000}` (years)
- After each step, adjust scale based on state change magnitude and wildcard events
- Track cumulative time in metadata, not step count

**Tradeoff:** Adds complexity to step interpretation. May need scenario-specific tuning.

---

### Tier 4: Visualization Improvements (user goal, low eval impact)

Research did not find specific best practices for simulation trajectory visualization beyond standard time series plotting. The project already has `visualize.py` with matplotlib-based plots.

**Recommendations (based on existing structure):**
- Add interactive plots with Plotly (hoverable state values, zoom timeline)
- Add `minimal-agora visualize` CLI subcommand (currently only programmatic)
- Generate HTML dashboard for completed runs (state timelines, outcome distribution, agent calibration if #35 implemented)

---

## Summary: Prioritized Hypothesis Roadmap

**Immediate (Cycle 1):**
1. ✅ Fix type_check dimension - enable pydantic.mypy, fix 16 errors (**+0.125**)
2. ✅ Improve observability - add structlog, instrument board/analysis/scenario (**+0.043**)
3. ✅ Fix issue #40 - resampling critic inline prompt migration (bug fix)

**Expected Result:** Composite score 0.711, exceeds 0.60 threshold.

**High-Value (Cycle 2):**
4. Issue #36 - State schema validation (correctness)
5. Issue #29 - Narrative compression (enables long simulations)
6. Issue #44 - Temperature scheduling (better exploration)

**Performance Optimizations (Cycle 3):**
7. Issue #32 - ESS-based resampling (smarter particle filtering)
8. Issue #30 - Adaptive review interval (fewer LLM calls)
9. Issue #42 - Multi-resolution stepping (10-50x speedup for long timescales)

**Growth Dimensions Addressed:**
- **Observability** - Tier 1.2 (structlog instrumentation)
- **Capability Surface** - Tier 2 (state validation, narrative compression, temperature scheduling expand what simulations can handle)

---

## References

**Type Safety:**
- [Pydantic Mypy Integration](https://pydantic.dev/docs/validation/latest/integrations/dev-tools/mypy/)
- [Type Safety in Python 2026](https://dasroot.net/posts/2026/02/type-safety-python-mypy-pydantic-runtime-validation/)

**Structured Logging:**
- [Structured Logging Best Practices for Production 2026](https://www.grepr.ai/blog/structured-logging-best-practices)
- [Python Logging Best Practices: structlog vs loguru](https://tutorials.technology/tutorials/python-logging-best-practices-structlog-loguru-2026.html)
- [structlog Documentation](https://www.structlog.org/en/stable/logging-best-practices.html)

**Particle Filtering:**
- [particles: Sequential Monte Carlo in Python](https://github.com/nchopin/particles)
- [Particle Filters in Python: Complete Guide](https://python.plainenglish.io/particle-filters-in-python-a-complete-guide-to-sequential-monte-carlo-methods-with-visualization-2c65a627ad03)

**Multi-Agent Debate:**
- [Can LLM Agents Really Debate? Controlled Study](https://arxiv.org/html/2511.07784v1)
- [Multi-Agent Debate Frameworks](https://www.emergentmind.com/topics/multi-agent-debate-mad-frameworks)
- [Improving Factuality with Multiagent Debate](https://composable-models.github.io/llm_debate/)

**Adaptive Time Stepping:**
- [Adaptive Time-Stepping Methods](https://www.emergentmind.com/topics/adaptive-time-stepping-methods)
- [Adaptive Local Time-Stepping for Multiresolution](https://www.sciencedirect.com/science/article/pii/S259005521930054X)
