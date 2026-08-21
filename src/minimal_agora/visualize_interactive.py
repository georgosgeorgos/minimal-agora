"""Interactive Plotly visualizations for simulation results.

Generates standalone HTML files with interactive charts for outcome
distributions, state-space trajectories, field timelines, constraint
evaluator scores, and token usage.
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from minimal_agora.analysis import (
    compute_agent_calibration,
    compute_outcome_coverage,
    load_trajectories,
)
from minimal_agora.models import Trajectory

logger = structlog.stdlib.get_logger(__name__)

try:
    import plotly.graph_objects as go  # type: ignore[import-not-found]
    from plotly.subplots import make_subplots  # type: ignore[import-not-found]

    _HAS_PLOTLY = True
except ImportError:
    _HAS_PLOTLY = False


COLORS = [
    "#00FF88", "#FF6B35", "#00D4FF", "#FF3CAC", "#FFD700",
    "#7BFF00", "#FF4466", "#00FFCC", "#C77DFF", "#FF9F1C",
]


def _require_plotly() -> None:
    if not _HAS_PLOTLY:
        raise RuntimeError(
            "plotly not installed — install with: pip install 'minimal-agora[viz]'"
        )


def _flatten_state(state: dict, prefix: str = "") -> dict[str, float]:
    flat: dict[str, float] = {}
    for k, v in state.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            flat.update(_flatten_state(v, key))
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            flat[key] = float(v)
    return flat


def _discover_numeric_fields(trajectories: list[Trajectory]) -> list[str]:
    fields: set[str] = set()
    for t in trajectories:
        for step in t.steps[:5]:
            fields.update(_flatten_state(step.state_after).keys())
    return sorted(fields)


def _outcome_color_map(trajectories: list[Trajectory]) -> dict[str, str]:
    outcomes = sorted({t.outcome.classification for t in trajectories if t.outcome})
    return {o: COLORS[i % len(COLORS)] for i, o in enumerate(outcomes)}


def plot_outcome_distribution(trajectories: list[Trajectory]) -> go.Figure:
    _require_plotly()
    from collections import Counter

    counts = Counter(
        t.outcome.classification if t.outcome else "unclassified"
        for t in trajectories
    )
    names = sorted(counts.keys())
    values = [counts[n] for n in names]
    total = sum(values)
    rates = [v / total if total else 0 for v in values]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=names, y=rates,
        text=[f"{v}/{total}" for v in values],
        textposition="auto",
        marker_color=[COLORS[i % len(COLORS)] for i in range(len(names))],
        hovertemplate="%{x}: %{text} (%{y:.1%})<extra></extra>",
    ))
    fig.update_layout(
        title="Outcome Distribution",
        xaxis_title="Outcome",
        yaxis_title="Rate",
        yaxis_tickformat=".0%",
        template="plotly_dark",
        height=400,
    )
    return fig


def plot_state_trajectories_3d(
    trajectories: list[Trajectory],
    x_field: str,
    y_field: str,
    z_field: str,
) -> go.Figure:
    _require_plotly()
    color_map = _outcome_color_map(trajectories)

    fig = go.Figure()
    for i, t in enumerate(trajectories):
        outcome = t.outcome.classification if t.outcome else "unclassified"
        xs, ys, zs, hovers = [], [], [], []
        for step in t.steps:
            flat = _flatten_state(step.state_after)
            x_val = flat.get(x_field)
            y_val = flat.get(y_field)
            z_val = flat.get(z_field)
            if x_val is not None and y_val is not None and z_val is not None:
                xs.append(x_val)
                ys.append(y_val)
                zs.append(z_val)
                hovers.append(f"Step {step.step_number}<br>{outcome}")

        color = color_map.get(outcome, COLORS[i % len(COLORS)])
        fig.add_trace(go.Scatter3d(
            x=xs, y=ys, z=zs,
            mode="lines+markers",
            marker={"size": 2, "color": color},
            line={"color": color, "width": 2},
            name=f"T{i} ({outcome})",
            hovertext=hovers,
            hoverinfo="text",
        ))

    fig.update_layout(
        title="State-Space Trajectories",
        scene={
            "xaxis_title": x_field,
            "yaxis_title": y_field,
            "zaxis_title": z_field,
        },
        template="plotly_dark",
        height=600,
    )
    return fig


def plot_field_timelines(
    trajectories: list[Trajectory],
    fields: list[str],
) -> go.Figure:
    _require_plotly()
    n_fields = len(fields)
    fig = make_subplots(
        rows=n_fields, cols=1,
        shared_xaxes=True,
        subplot_titles=fields,
        vertical_spacing=0.05,
    )
    color_map = _outcome_color_map(trajectories)

    for i, t in enumerate(trajectories):
        outcome = t.outcome.classification if t.outcome else "unclassified"
        color = color_map.get(outcome, COLORS[i % len(COLORS)])
        for row, field in enumerate(fields, 1):
            steps_x, vals_y = [], []
            for step in t.steps:
                flat = _flatten_state(step.state_after)
                val = flat.get(field)
                if val is not None:
                    steps_x.append(step.step_number)
                    vals_y.append(val)

            fig.add_trace(
                go.Scatter(
                    x=steps_x, y=vals_y,
                    mode="lines",
                    line={"color": color, "width": 1},
                    name=f"T{i}" if row == 1 else None,
                    legendgroup=f"T{i}",
                    showlegend=(row == 1),
                    hovertemplate=f"T{i} step %{{x}}: %{{y:.3f}}<extra>{field}</extra>",
                ),
                row=row, col=1,
            )

    fig.update_layout(
        title="State Field Timelines",
        height=200 * n_fields + 100,
        template="plotly_dark",
        xaxis_title="Step",
    )
    return fig


def plot_constraint_scores(trajectories: list[Trajectory]) -> go.Figure | None:
    _require_plotly()
    categories = ["physical", "consistency", "pacing", "rules"]
    has_data = False

    fig = make_subplots(
        rows=1, cols=1,
    )

    for i, t in enumerate(trajectories):
        cat_steps: dict[str, list[int]] = {c: [] for c in categories}
        cat_vals: dict[str, list[float]] = {c: [] for c in categories}

        for step in t.steps:
            for crit in step.critiques:
                if crit.scores:
                    has_data = True
                    for cat in categories:
                        if cat in crit.scores:
                            cat_steps[cat].append(step.step_number)
                            cat_vals[cat].append(crit.scores[cat])

        for j, cat in enumerate(categories):
            if cat_steps[cat]:
                fig.add_trace(go.Scatter(
                    x=cat_steps[cat], y=cat_vals[cat],
                    mode="lines+markers",
                    marker={"size": 4},
                    name=f"{cat} (T{i})" if len(trajectories) > 1 else cat,
                    line={"color": COLORS[j % len(COLORS)]},
                    hovertemplate=f"{cat}: %{{y:.2f}} (step %{{x}})<extra>T{i}</extra>",
                ))

    if not has_data:
        return None

    fig.update_layout(
        title="Constraint Evaluator Scores Over Time",
        xaxis_title="Step",
        yaxis_title="Score",
        yaxis_range=[0, 1.05],
        template="plotly_dark",
        height=400,
    )
    return fig


def plot_token_usage(trajectories: list[Trajectory]) -> go.Figure:
    _require_plotly()
    fig = go.Figure()

    for i, t in enumerate(trajectories):
        steps_x, input_y, output_y = [], [], []
        for step in t.steps:
            if step.token_usage:
                steps_x.append(step.step_number)
                input_y.append(step.token_usage.total_input_tokens or 0)
                output_y.append(step.token_usage.total_output_tokens or 0)

        fig.add_trace(go.Bar(
            x=steps_x, y=input_y,
            name=f"Input (T{i})",
            marker_color=COLORS[0],
            opacity=0.7,
            hovertemplate="Step %{x}: %{y:,} input tokens<extra></extra>",
        ))
        fig.add_trace(go.Bar(
            x=steps_x, y=output_y,
            name=f"Output (T{i})",
            marker_color=COLORS[1],
            opacity=0.7,
            hovertemplate="Step %{x}: %{y:,} output tokens<extra></extra>",
        ))

    fig.update_layout(
        title="Token Usage Per Step",
        xaxis_title="Step",
        yaxis_title="Tokens",
        barmode="stack",
        template="plotly_dark",
        height=400,
    )
    return fig


def plot_proposal_conflicts(trajectories: list[Trajectory]) -> go.Figure:
    _require_plotly()
    fig = go.Figure()

    for i, t in enumerate(trajectories):
        review_steps, auto_steps, conflict_steps = [], [], []
        for step in t.steps:
            s = step.step_number
            if step.critiques:
                review_steps.append(s)
            elif step.resolution is not None:
                conflict_steps.append(s)
            else:
                auto_steps.append(s)

        fig.add_trace(go.Scatter(
            x=auto_steps,
            y=[i] * len(auto_steps),
            mode="markers",
            marker={"size": 6, "color": "#00FF88", "symbol": "circle"},
            name="Auto-merge" if i == 0 else None,
            legendgroup="auto",
            showlegend=(i == 0),
            hovertemplate="Step %{x}: auto-merge<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=conflict_steps,
            y=[i] * len(conflict_steps),
            mode="markers",
            marker={"size": 8, "color": "#FFD700", "symbol": "diamond"},
            name="Conflict → resolver" if i == 0 else None,
            legendgroup="conflict",
            showlegend=(i == 0),
            hovertemplate="Step %{x}: conflict resolution<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=review_steps,
            y=[i] * len(review_steps),
            mode="markers",
            marker={"size": 8, "color": "#FF3CAC", "symbol": "star"},
            name="Full review" if i == 0 else None,
            legendgroup="review",
            showlegend=(i == 0),
            hovertemplate="Step %{x}: full review<extra></extra>",
        ))

    fig.update_layout(
        title="Resolution Path Per Step",
        xaxis_title="Step",
        yaxis_title="Trajectory",
        template="plotly_dark",
        height=max(300, 80 * len(trajectories) + 100),
    )
    return fig


def plot_agent_calibration(trajectories: list[Trajectory]) -> go.Figure | None:
    """Create agent calibration charts: grouped bars and calibration scatter.

    Returns a figure with two subplots:
      1. Grouped bar chart: acceptance_rate vs mean_confidence per agent
      2. Scatter: confidence vs acceptance_rate (diagonal = perfect calibration)
    """
    _require_plotly()
    calibration = compute_agent_calibration(trajectories)
    if not calibration:
        return None

    agents = sorted(calibration.keys())
    acceptance_rates = [calibration[a]["acceptance_rate"] for a in agents]
    mean_confidences = [calibration[a]["mean_confidence"] for a in agents]

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=["Acceptance Rate vs Confidence", "Calibration Plot"],
        horizontal_spacing=0.12,
    )

    # Grouped bar chart
    fig.add_trace(
        go.Bar(
            x=agents,
            y=acceptance_rates,
            name="Acceptance Rate",
            marker_color=COLORS[2],
            hovertemplate="%{x}: %{y:.1%}<extra>Acceptance Rate</extra>",
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Bar(
            x=agents,
            y=mean_confidences,
            name="Mean Confidence",
            marker_color=COLORS[0],
            hovertemplate="%{x}: %{y:.2f}<extra>Mean Confidence</extra>",
        ),
        row=1, col=1,
    )

    # Calibration scatter
    fig.add_trace(
        go.Scatter(
            x=[0, 1], y=[0, 1],
            mode="lines",
            line={"color": "rgba(255,255,255,0.3)", "dash": "dash"},
            name="Perfect Calibration",
            hoverinfo="skip",
        ),
        row=1, col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=mean_confidences,
            y=acceptance_rates,
            mode="markers+text",
            marker={"size": 12, "color": COLORS[3]},
            text=agents,
            textposition="top center",
            textfont={"size": 10},
            name="Agents",
            hovertemplate=(
                "%{text}<br>Confidence: %{x:.2f}<br>Acceptance: %{y:.1%}"
                "<extra></extra>"
            ),
        ),
        row=1, col=2,
    )

    fig.update_xaxes(title_text="Agent", row=1, col=1)
    fig.update_yaxes(title_text="Rate", tickformat=".0%", row=1, col=1)
    fig.update_xaxes(title_text="Mean Confidence", range=[0, 1.05], row=1, col=2)
    fig.update_yaxes(title_text="Acceptance Rate", range=[0, 1.05], tickformat=".0%", row=1, col=2)

    fig.update_layout(
        title="Agent Calibration",
        barmode="group",
        template="plotly_dark",
        height=450,
    )
    return fig


def plot_outcome_coverage(trajectories: list[Trajectory]) -> go.Figure | None:
    """Visualize outcome space coverage with a grouped bar chart and PCA scatter.

    Returns a figure with two subplots:
      1. Grouped bars showing normalized_entropy, state_space_coverage, trajectory_divergence
      2. 2D scatter of final states projected onto the first two principal components
    """
    _require_plotly()
    import numpy as np

    metrics = compute_outcome_coverage(trajectories)
    if not trajectories:
        return None

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=["Coverage Dimensions", "Final States (PCA)"],
        horizontal_spacing=0.12,
    )

    # --- Grouped bar chart of coverage dimensions ---
    dim_names = ["Normalized Entropy", "State Space Coverage", "Trajectory Divergence"]
    dim_values = [
        metrics["normalized_entropy"],
        min(1.0, metrics["state_space_coverage"]),
        min(1.0, metrics["trajectory_divergence"] / max(1.0, metrics["trajectory_divergence"])),
    ]

    fig.add_trace(
        go.Bar(
            x=dim_names,
            y=dim_values,
            marker_color=[COLORS[0], COLORS[2], COLORS[4]],
            hovertemplate="%{x}: %{y:.3f}<extra></extra>",
            showlegend=False,
        ),
        row=1, col=1,
    )

    # Add a horizontal line for the combined coverage score
    fig.add_hline(
        y=metrics["coverage_score"],
        line_dash="dash",
        line_color="rgba(255,255,255,0.5)",
        annotation_text=f"Coverage Score: {metrics['coverage_score']:.3f}",
        annotation_position="top right",
        row=1, col=1,
    )

    # --- PCA scatter of final states ---
    flat_states: list[dict[str, float]] = []
    outcome_labels: list[str] = []
    traj_ids: list[int] = []
    for t in trajectories:
        final = t.outcome.final_state if t.outcome else {}
        flat_states.append(_flatten_state(final))
        outcome_labels.append(t.outcome.classification if t.outcome else "unclassified")
        traj_ids.append(t.trajectory_id)

    # Collect all numeric keys across all final states
    all_keys = sorted({k for fs in flat_states for k in fs})

    if len(all_keys) >= 2 and len(flat_states) >= 2:
        # Build feature matrix
        matrix = np.array([
            [fs.get(k, 0.0) for k in all_keys]
            for fs in flat_states
        ])

        # Center the data
        mean = matrix.mean(axis=0)
        centered = matrix - mean

        # PCA via SVD
        try:
            _u, _s, vt = np.linalg.svd(centered, full_matrices=False)
            projected = centered @ vt[:2].T

            color_map = {}
            unique_outcomes = sorted(set(outcome_labels))
            for idx, o in enumerate(unique_outcomes):
                color_map[o] = COLORS[idx % len(COLORS)]

            for outcome in unique_outcomes:
                mask = [i for i, o in enumerate(outcome_labels) if o == outcome]
                fig.add_trace(
                    go.Scatter(
                        x=[float(projected[i, 0]) for i in mask],
                        y=[float(projected[i, 1]) for i in mask],
                        mode="markers+text",
                        marker={"size": 10, "color": color_map[outcome]},
                        text=[f"T{traj_ids[i]}" for i in mask],
                        textposition="top center",
                        textfont={"size": 9},
                        name=outcome,
                        hovertemplate=(
                            "T%{text}<br>PC1: %{x:.3f}<br>PC2: %{y:.3f}"
                            "<extra></extra>"
                        ),
                    ),
                    row=1, col=2,
                )
        except np.linalg.LinAlgError:
            pass  # SVD did not converge; skip PCA plot

    fig.update_xaxes(title_text="Dimension", row=1, col=1)
    fig.update_yaxes(title_text="Value", range=[0, 1.1], row=1, col=1)
    fig.update_xaxes(title_text="PC1", row=1, col=2)
    fig.update_yaxes(title_text="PC2", row=1, col=2)

    fig.update_layout(
        title="Outcome Space Coverage",
        template="plotly_dark",
        height=450,
    )
    return fig


def generate_interactive_report(
    run_dir: Path,
    fields: list[str] | None = None,
    output_path: Path | None = None,
) -> Path:
    _require_plotly()
    trajectories = load_trajectories(run_dir)
    if not trajectories:
        raise ValueError(f"No trajectories found in {run_dir}")

    if fields is None:
        fields = _discover_numeric_fields(trajectories)[:6]

    report_json = None
    report_path = run_dir / "report.json"
    if report_path.exists():
        report_json = json.loads(report_path.read_text())

    figs: list[go.Figure] = []

    figs.append(plot_outcome_distribution(trajectories))

    if len(fields) >= 3:
        figs.append(plot_state_trajectories_3d(
            trajectories, fields[0], fields[1], fields[2],
        ))

    if fields:
        figs.append(plot_field_timelines(trajectories, fields))

    figs.append(plot_proposal_conflicts(trajectories))

    scores_fig = plot_constraint_scores(trajectories)
    if scores_fig:
        figs.append(scores_fig)

    figs.append(plot_token_usage(trajectories))

    cal_fig = plot_agent_calibration(trajectories)
    if cal_fig:
        figs.append(cal_fig)

    coverage_fig = plot_outcome_coverage(trajectories)
    if coverage_fig:
        figs.append(coverage_fig)

    scenario_name = report_json.get("scenario_name", "unknown") if report_json else "unknown"
    question = report_json.get("question", "") if report_json else ""

    html_parts = [
        "<!DOCTYPE html>",
        "<html><head>",
        f"<title>{scenario_name} — Interactive Report</title>",
        '<meta charset="utf-8">',
        '<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>',
        "<style>",
        "body { background: #111; color: #eee; font-family: system-ui; margin: 0; padding: 20px; }",
        "h1 { margin-bottom: 5px; }",
        ".subtitle { color: #888; margin-bottom: 30px; }",
        ".chart { margin-bottom: 30px; }",
        "</style>",
        "</head><body>",
        f"<h1>{scenario_name}</h1>",
        f'<p class="subtitle">{question}</p>',
    ]

    for i, fig in enumerate(figs):
        div_id = f"chart-{i}"
        html_parts.append(f'<div id="{div_id}" class="chart"></div>')
        fig_json = fig.to_json()
        html_parts.append(f"<script>Plotly.newPlot('{div_id}', {fig_json});</script>")

    html_parts.append("</body></html>")

    out = output_path or (run_dir / "report_interactive.html")
    out.write_text("\n".join(html_parts))
    logger.info("interactive_report.written", path=str(out), n_charts=len(figs))
    return out
