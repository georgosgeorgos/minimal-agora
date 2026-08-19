from __future__ import annotations

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
                num_vals: list[int | float] = []
                num_steps: list[int] = []
                for s in t.steps:
                    val = _get_nested(s.state_after, field)
                    if isinstance(val, (int, float)):
                        num_vals.append(val)
                        num_steps.append(s.step_number)
                if num_vals:
                    color = COLORS[t_idx % len(COLORS)]
                    ax.plot(num_steps, num_vals, marker="o", markersize=3,
                            color=color, alpha=0.6, label=f"traj {t.trajectory_id}")

            means: list[float | None] = []
            for step_key in steps:
                vals = [v for v in field_data[step_key] if isinstance(v, (int, float))]
                if vals:
                    means.append(sum(vals) / len(vals))
                else:
                    means.append(None)

            valid_steps = [sk for sk, m in zip(steps, means) if m is not None]
            valid_means = [m for m in means if m is not None]
            if valid_means:
                ax.plot(valid_steps, valid_means, "k-", linewidth=2, label="mean", zorder=10)
        else:
            for t_idx, t in enumerate(trajectories):
                str_vals: list[str] = []
                str_steps: list[int] = []
                for s in t.steps:
                    val = _get_nested(s.state_after, field)
                    if val is not None:
                        str_vals.append(str(val))
                        str_steps.append(s.step_number)
                if str_vals:
                    ax.scatter(str_steps, str_vals, marker="o", s=30,
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
        vals = steps_by_outcome[label]
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


def generate_all_plots(
    output_dir: Path,
    fields: list[str] | None = None,
    populations: list[str] | None = None,
    score_fields: list[str] | None = None,
) -> list[Path]:
    trajectories = load_trajectories(output_dir)
    if not trajectories:
        print(f"No trajectories found in {output_dir}")
        return []

    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    generated = []

    path = plot_outcome_distribution(trajectories, plots_dir / "outcome_distribution.png")
    generated.append(path)
    print(f"  Generated: {path}")

    path = plot_step_distribution(trajectories, plots_dir / "step_distribution.png")
    generated.append(path)
    print(f"  Generated: {path}")

    if fields:
        path = plot_field_timelines(trajectories, fields, plots_dir / "field_timelines.png")
        generated.append(path)
        print(f"  Generated: {path}")

    if populations and score_fields:
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
