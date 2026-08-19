from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from minimal_agora.analysis import (
    compute_statistics,
    extract_field_timelines,
    load_trajectories,
)
from minimal_agora.models import Trajectory

COLORS = [
    "#2196F3", "#F44336", "#4CAF50", "#FF9800", "#9C27B0",
    "#00BCD4", "#795548", "#607D8B", "#E91E63", "#3F51B5",
]


def plot_outcome_distribution(
    trajectories: list[Trajectory], output_path: Path,
) -> Path:
    if not trajectories:
        return output_path

    outcomes: dict[str, int] = {}
    for t in trajectories:
        cls = t.outcome.classification if t.outcome else "unclassified"
        outcomes[cls] = outcomes.get(cls, 0) + 1

    labels = sorted(outcomes.keys())
    counts = [outcomes[l] for l in labels]
    n = len(trajectories)

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(labels, counts, color=COLORS[: len(labels)], edgecolor="white", linewidth=0.5)

    for bar, count in zip(bars, counts):
        ax.text(
            bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
            f"{count}/{n}\n({count / n:.0%})", ha="center", va="bottom", fontsize=9,
        )

    scenario = trajectories[0].scenario_name if trajectories else "unknown"
    ax.set_title(f"{scenario} — Outcome Distribution (n={n})", fontsize=12, fontweight="bold")
    ax.set_ylabel("Count")
    ax.set_xlabel("Outcome")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def plot_field_timelines(
    trajectories: list[Trajectory], fields: list[str], output_path: Path,
) -> Path:
    if not trajectories or not fields:
        return output_path

    timelines = extract_field_timelines(trajectories, fields)
    n_fields = len(fields)
    fig, axes = plt.subplots(n_fields, 1, figsize=(10, 4 * n_fields), squeeze=False)

    for i, field in enumerate(fields):
        ax = axes[i, 0]
        field_data = timelines[field]

        if not field_data:
            ax.set_title(f"{field} — no data")
            continue

        steps = sorted(field_data.keys())

        numeric = all(
            isinstance(v, (int, float))
            for step_vals in field_data.values()
            for v in step_vals
        )

        if numeric:
            for t_idx, t in enumerate(trajectories):
                t_vals = []
                t_steps = []
                for step in t.steps:
                    val = _get_nested(step.state_after, field)
                    if isinstance(val, (int, float)):
                        t_vals.append(val)
                        t_steps.append(step.step_number)
                if t_vals:
                    color = COLORS[t_idx % len(COLORS)]
                    ax.plot(t_steps, t_vals, marker="o", markersize=3,
                            color=color, alpha=0.6, label=f"traj {t.trajectory_id}")

            means: list[float | None] = []
            for step_num in steps:
                vals = [v for v in field_data[step_num] if isinstance(v, (int, float))]
                if vals:
                    means.append(sum(vals) / len(vals))
                else:
                    means.append(None)

            valid_steps = [s for s, m in zip(steps, means) if m is not None]
            valid_means = [m for m in means if m is not None]
            if valid_means:
                ax.plot(valid_steps, valid_means, "k-", linewidth=2, label="mean", zorder=10)
        else:
            for t_idx, t in enumerate(trajectories):
                cat_vals: list[str] = []
                cat_steps: list[int] = []
                for step in t.steps:
                    val = _get_nested(step.state_after, field)
                    if val is not None:
                        cat_vals.append(str(val))
                        cat_steps.append(step.step_number)
                if cat_vals:
                    ax.scatter(cat_steps, cat_vals, marker="o", s=30,
                               color=COLORS[t_idx % len(COLORS)], alpha=0.6)

        ax.set_title(field, fontsize=11, fontweight="bold")
        ax.set_xlabel("Step")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        if numeric and len(trajectories) <= 10:
            ax.legend(fontsize=7, loc="best")

    scenario = trajectories[0].scenario_name if trajectories else "unknown"
    fig.suptitle(f"{scenario} — Field Timelines", fontsize=13, fontweight="bold", y=1.01)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_step_distribution(
    trajectories: list[Trajectory], output_path: Path,
) -> Path:
    if not trajectories:
        return output_path

    steps_by_outcome: dict[str, list[int]] = {}
    for t in trajectories:
        cls = t.outcome.classification if t.outcome else "unclassified"
        steps_by_outcome.setdefault(cls, []).append(len(t.steps))

    fig, ax = plt.subplots(figsize=(8, 5))
    labels = sorted(steps_by_outcome.keys())

    for i, label in enumerate(labels):
        vals: Sequence[float | int] = steps_by_outcome[label]
        stats = compute_statistics(vals)
        ax.bar(
            i, stats.get("mean", 0), color=COLORS[i % len(COLORS)],
            edgecolor="white", linewidth=0.5, label=label,
        )
        if stats.get("std", 0) > 0:
            ax.errorbar(i, stats["mean"], yerr=stats["std"], color="black", capsize=4, linewidth=1)

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels)
    ax.set_ylabel("Steps to outcome (mean ± std)")
    ax.set_title("Steps to Outcome by Classification", fontsize=12, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def plot_population_scores(
    trajectories: list[Trajectory], populations: list[str],
    score_field: str, output_path: Path,
) -> Path:
    if not trajectories or not populations:
        return output_path

    fig, ax = plt.subplots(figsize=(10, 6))

    for pop_idx, pop in enumerate(populations):
        field = f"populations.{pop}.{score_field}"
        color = COLORS[pop_idx % len(COLORS)]

        all_steps: dict[int, list[float]] = {}
        for t in trajectories:
            for step in t.steps:
                val = _get_nested(step.state_after, field)
                if isinstance(val, (int, float)):
                    all_steps.setdefault(step.step_number, []).append(val)

        if all_steps:
            steps = sorted(all_steps.keys())
            means = [sum(all_steps[s]) / len(all_steps[s]) for s in steps]
            ax.plot(steps, means, marker="o", markersize=4, color=color, linewidth=2, label=pop)

            if len(trajectories) > 1:
                mins = [min(all_steps[s]) for s in steps]
                maxs = [max(all_steps[s]) for s in steps]
                ax.fill_between(steps, mins, maxs, color=color, alpha=0.1)

    ax.set_xlabel("Step")
    ax.set_ylabel(score_field)
    ax.set_title(f"Population {score_field} Over Time", fontsize=12, fontweight="bold")
    ax.legend()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def plot_trajectory_comparison(
    trajectories: list[Trajectory], fields: list[str], output_path: Path,
) -> Path:
    if not trajectories or not fields:
        return output_path

    n_fields = len(fields)
    fig, axes = plt.subplots(n_fields, 1, figsize=(10, 4 * n_fields), squeeze=False)

    for i, field in enumerate(fields):
        ax = axes[i, 0]

        for t_idx, t in enumerate(trajectories):
            t_vals = []
            t_steps = []
            for step in t.steps:
                val = _get_nested(step.state_after, field)
                if isinstance(val, (int, float)):
                    t_vals.append(val)
                    t_steps.append(step.step_number)
            if t_vals:
                color = COLORS[t_idx % len(COLORS)]
                ax.plot(t_steps, t_vals, marker="o", markersize=4,
                        color=color, linewidth=1.5, label=f"T{t.trajectory_id}")

        ax.set_title(field, fontsize=11, fontweight="bold")
        ax.set_xlabel("Step")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.legend(fontsize=8, loc="best")

    scenario = trajectories[0].scenario_name if trajectories else "unknown"
    fig.suptitle(f"{scenario} — Trajectory Comparison", fontsize=13, fontweight="bold", y=1.01)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_wildcard_impact(
    trajectories: list[Trajectory], output_path: Path,
) -> Path:
    if not trajectories:
        return output_path

    events: dict[int, list[int]] = {}
    max_step = 0

    for t in trajectories:
        t_events = []
        for j in range(1, len(t.steps)):
            if t.steps[j - 1].state_after != t.steps[j].state_before:
                t_events.append(t.steps[j].step_number)
        events[t.trajectory_id] = t_events
        for s in t.steps:
            max_step = max(max_step, s.step_number)

    t_ids = sorted(events.keys())
    n_rows = len(t_ids)
    fig_height = max(4, n_rows * 0.5 + 3)
    fig, (ax_main, ax_freq) = plt.subplots(
        2, 1, figsize=(10, fig_height), gridspec_kw={"height_ratios": [3, 1]},
    )

    for y_idx, tid in enumerate(t_ids):
        steps_with_events = events[tid]
        if steps_with_events:
            ax_main.scatter(
                steps_with_events, [y_idx] * len(steps_with_events),
                color=COLORS[4], s=60, zorder=5, marker="D",
            )
        ax_main.axhline(y=y_idx, color="#E0E0E0", linewidth=0.5, zorder=0)

    ax_main.set_yticks(range(n_rows))
    ax_main.set_yticklabels([f"T{tid}" for tid in t_ids])
    ax_main.set_xlim(-0.5, max_step + 0.5)
    ax_main.set_xlabel("Step")
    ax_main.set_title("Wildcard Events by Trajectory", fontsize=11, fontweight="bold")
    ax_main.spines["top"].set_visible(False)
    ax_main.spines["right"].set_visible(False)

    freq = [0] * (max_step + 1)
    for t_events in events.values():
        for s in t_events:
            if s <= max_step:
                freq[s] += 1

    ax_freq.bar(range(max_step + 1), freq, color=COLORS[4], alpha=0.7)
    ax_freq.set_xlabel("Step")
    ax_freq.set_ylabel("Count")
    ax_freq.set_title("Aggregate Wildcard Frequency", fontsize=10)
    ax_freq.spines["top"].set_visible(False)
    ax_freq.spines["right"].set_visible(False)

    scenario = trajectories[0].scenario_name if trajectories else "unknown"
    fig.suptitle(f"{scenario} — Wildcard Impact", fontsize=13, fontweight="bold", y=1.02)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_agent_activity(
    trajectories: list[Trajectory], output_path: Path,
) -> Path:
    if not trajectories:
        return output_path

    agent_stats: dict[str, dict] = {}

    for t in trajectories:
        for step in t.steps:
            accepted_agents: set[str] = set()
            if step.resolution and step.resolution.state_delta:
                for p in step.proposals:
                    if any(k in step.resolution.state_delta for k in p.proposed_changes):
                        accepted_agents.add(p.agent)

            for p in step.proposals:
                if p.agent not in agent_stats:
                    agent_stats[p.agent] = {
                        "proposals": 0, "accepted": 0,
                        "plausibility_sum": 0.0, "plausibility_count": 0,
                    }
                agent_stats[p.agent]["proposals"] += 1
                if p.agent in accepted_agents:
                    agent_stats[p.agent]["accepted"] += 1

            for c in step.critiques:
                for target in c.target_proposals:
                    if target in agent_stats:
                        agent_stats[target]["plausibility_sum"] += c.plausibility
                        agent_stats[target]["plausibility_count"] += 1

    if not agent_stats:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "No agent activity data", ha="center", va="center", fontsize=12)
        ax.set_axis_off()
        fig.savefig(output_path, dpi=150)
        plt.close(fig)
        return output_path

    agents = sorted(agent_stats.keys())
    n_proposals = [agent_stats[a]["proposals"] for a in agents]
    acceptance_rates = [
        agent_stats[a]["accepted"] / agent_stats[a]["proposals"]
        if agent_stats[a]["proposals"] > 0 else 0
        for a in agents
    ]
    avg_plausibility = [
        agent_stats[a]["plausibility_sum"] / agent_stats[a]["plausibility_count"]
        if agent_stats[a]["plausibility_count"] > 0 else 0
        for a in agents
    ]

    fig_height = max(4, len(agents) * 0.5 + 1)
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(14, fig_height))
    y_pos = list(range(len(agents)))

    ax1.barh(y_pos, n_proposals, color=COLORS[0], edgecolor="white", linewidth=0.5)
    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(agents)
    ax1.set_xlabel("Count")
    ax1.set_title("Total Proposals", fontsize=10, fontweight="bold")
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)

    ax2.barh(y_pos, acceptance_rates, color=COLORS[1], edgecolor="white", linewidth=0.5)
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels([])
    ax2.set_xlabel("Rate")
    ax2.set_xlim(0, 1)
    ax2.set_title("Acceptance Rate", fontsize=10, fontweight="bold")
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)

    ax3.barh(y_pos, avg_plausibility, color=COLORS[2], edgecolor="white", linewidth=0.5)
    ax3.set_yticks(y_pos)
    ax3.set_yticklabels([])
    ax3.set_xlabel("Score")
    ax3.set_xlim(0, 1)
    ax3.set_title("Avg Plausibility", fontsize=10, fontweight="bold")
    ax3.spines["top"].set_visible(False)
    ax3.spines["right"].set_visible(False)

    scenario = trajectories[0].scenario_name if trajectories else "unknown"
    fig.suptitle(f"{scenario} — Agent Activity", fontsize=12, fontweight="bold")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


def generate_all_plots(
    output_dir: Path,
    fields: list[str] | None = None,
    populations: list[str] | None = None,
    score_fields: list[str] | None = None,
    plot_types: list[str] | None = None,
) -> list[Path]:
    trajectories = load_trajectories(output_dir)
    if not trajectories:
        print(f"No trajectories found in {output_dir}")
        return []

    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    generated = []
    want = set(plot_types) if plot_types else None

    def _should(name: str) -> bool:
        return want is None or name in want

    if _should("outcomes"):
        path = plot_outcome_distribution(trajectories, plots_dir / "outcome_distribution.png")
        generated.append(path)
        print(f"  Generated: {path}")

    if _should("steps"):
        path = plot_step_distribution(trajectories, plots_dir / "step_distribution.png")
        generated.append(path)
        print(f"  Generated: {path}")

    if _should("wildcards"):
        path = plot_wildcard_impact(trajectories, plots_dir / "wildcard_impact.png")
        generated.append(path)
        print(f"  Generated: {path}")

    if _should("agents"):
        path = plot_agent_activity(trajectories, plots_dir / "agent_activity.png")
        generated.append(path)
        print(f"  Generated: {path}")

    if fields and _should("timelines"):
        path = plot_field_timelines(trajectories, fields, plots_dir / "field_timelines.png")
        generated.append(path)
        print(f"  Generated: {path}")

    if fields and _should("comparison"):
        path = plot_trajectory_comparison(trajectories, fields, plots_dir / "trajectory_comparison.png")
        generated.append(path)
        print(f"  Generated: {path}")

    if populations and score_fields and _should("populations"):
        for score_field in score_fields:
            fname = f"population_{score_field}.png"
            path = plot_population_scores(trajectories, populations, score_field, plots_dir / fname)
            generated.append(path)
            print(f"  Generated: {path}")

    return generated


def _get_nested(d: dict, path: str):
    keys = path.split(".")
    current = d
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current
