---
tags: [factory, experiment, minimal-agora]
project: minimal-agora
experiment_id: 004
verdict: keep
score_delta: +0.015
date: 2026-08-18
source: factory-archivist
---

# Experiment #004: Visualization improvements — new plot types for trajectory analytics

## Result
**KEEP** — score changed from 0.679 to 0.694 (+0.015). Three new visualization plot types implemented and fully tested (103/103 tests pass, 8 new tests). All QA checks passed.

## What Changed
- Implemented **Trajectory Comparison Plot** (`src/minimal_agora/analysis.py`): side-by-side trajectory heatmaps comparing final state divergence across N runs, highlights key decision branches
- Implemented **Wildcard Impact Plot**: shows correlation between wildcard event occurrence and outcome variance, identifies high-impact stochastic shocks
- Implemented **Agent Activity Heatmap**: visualizes which agents proposed/critiqued in each step, detects silent agents and role concentration
- Added `src/minimal_agora/visualize.py` module with Matplotlib-based rendering and PNG export
- Integrated plots into report generation pipeline (`src/minimal_agora/analysis.py:generate_report()`)
- Added 8 unit tests covering plot rendering, data aggregation, and edge cases (single trajectory, no wildcards, silent agents)
- Updated CLI with `--plots` flag to control which visualizations are generated
- PR #45 merged with clean lint, full coverage, no performance regressions

## What We Learned
Visual analytics are critical for understanding simulation behavior at scale. Raw data (state diffs, proposal logs) is overwhelming for N=50+ runs. Heatmaps and correlation plots let domain experts spot patterns: which wildcards destabilize vs stabilize, whether simulation is mono-modal (all runs converge) or multi-modal (diverge into distinct branches), which agents are actually influential vs decorative. The three plot types cover the most-requested analyses from prior simulation runs.

## Key Metrics
| Metric | Value |
|--------|-------|
| Tests Passing | 103/103 (100%) |
| Tests Added | 8 (plot rendering + data aggregation) |
| Lint Status | clean |
| Type Check | 1 pre-existing error (unchanged) |
| New Modules | 1 (visualize.py) |
| Plot Types Added | 3 |
| Render Speed | <500ms for N=50 trajectories |
| Output Format | PNG (high-res, 300dpi) |

## Links
- Related Issues: #30, #37 (visualization requests)
- PR: #45

## Technical Notes
- Plots use Matplotlib with seaborn styling for publication-quality output
- Trajectory comparison uses hierarchical clustering (linkage on final state L2 distance) to group similar outcomes
- Wildcard impact uses Pearson correlation between wildcard occurrence (0/1) and outcome variance per dimension
- Agent activity heatmap is a simple step×agent matrix with counts, colored by density
- All plots support filtering by agent role, outcome category, or time range
- PNG export includes metadata (timestamp, scenario name, N trajectories, plot type)

## Design Rationale
Simulations generate high-dimensional state trajectories — difficult to reason about without distillation. Heatmaps exploit human visual cortex's strength in detecting patterns, correlations, and outliers. Rather than 10 CSV tables, three strategic plots answer the most common analytical questions: "Did we converge?" (trajectory comparison), "What shocks mattered?" (wildcard impact), "Who decided?" (agent activity). This is essential for research iteration: quickly spot whether a hypothesis is working without manual log inspection.

