# Health Check Report

- **timestamp:** 2026-08-18
- **baseline_score:** 0.679
- **composite_score:** 0.694
- **gate:** PASS

---

## Score Table

| Dimension | Score | Weight | Status | Details |
|-----------|-------|--------|--------|---------|
| test_suite | 1.000 | 0.250 | PASS | 103 passed |
| test_coverage | 0.610 | 0.250 | PASS | coverage=61% |
| tests (factory) | 0.500 | 0.093 | PASS | Not detected (known issue) |
| coverage (factory) | 0.500 | 0.075 | PASS | Not detected (known issue) |
| capability_surface | 0.720 | 0.050 | PASS | surface=144, target=200 |
| lint | 0.900 | 0.045 | FAIL | 1 error |
| experiment_diversity | 0.500 | 0.040 | PASS | Only 2 experiments |
| observability | 0.359 | 0.036 | FAIL | function_coverage=0.17 |
| type_check | 0.950 | 0.030 | FAIL | 1 error |
| config_parser | 1.000 | 0.030 | PASS | All checks OK |
| research_grounding | 0.100 | 0.028 | FAIL | No research sources |
| architecture | 0.500 | 0.027 | PASS | No rules.toml |
| factory_effectiveness | 0.500 | 0.026 | PASS | Only 2 experiments |
| spec_compliance | 0.500 | 0.020 | PASS | Neutral (no spec_results.json) |

## Composite

- **Score:** 0.694
- **Baseline:** 0.679
- **Delta:** +0.015 (improvement)
- **Threshold:** ABOVE baseline

## Unit Tests

- **Status:** PASS
- **Result:** 103 passed, 0 failed, 0 errors
- **Runtime:** 1.14s
- **Breakdown:**
  - test_analysis.py: 5 passed
  - test_conditional_wildcards.py: 30 passed
  - test_models.py: 33 passed
  - test_narrative_compression.py: 11 passed (new)
  - test_resampling_critic.py: 11 passed
  - test_visualize.py: 13 passed (8 new)

## Guard Violations

None.

## Overall Gate Result

**PASS**

- Unit tests: 103/103 passing
- Composite score: 0.694 (above 0.679 baseline, +0.015 delta)
- No guard violations
- Eval returned valid JSON without errors
