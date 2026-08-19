from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from minimal_agora.models import CrossRunComparison, Trajectory


def plot_outcome_comparison(
    comparison: CrossRunComparison, output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    categories = [c["category"] for c in comparison.outcome_comparisons]
    rates_a = [c["rate_a"] for c in comparison.outcome_comparisons]
    rates_b = [c["rate_b"] for c in comparison.outcome_comparisons]

    if not categories:
        fig, ax = plt.subplots()
        ax.set_title("No outcome data")
        fig.savefig(output_path, dpi=150)
        plt.close(fig)
        return output_path

    x = np.arange(len(categories))
    width = 0.35

    ci_a = _wilson_cis(rates_a, comparison.n_trajectories_a)
    ci_b = _wilson_cis(rates_b, comparison.n_trajectories_b)

    fig, ax = plt.subplots(figsize=(max(8, len(categories) * 2), 5))
    ax.bar(
        x - width / 2, rates_a, width, label=comparison.run_a_name,
        color="#2196F3", edgecolor="white", linewidth=0.5,
        yerr=ci_a, capsize=4,
    )
    ax.bar(
        x + width / 2, rates_b, width, label=comparison.run_b_name,
        color="#F44336", edgecolor="white", linewidth=0.5,
        yerr=ci_b, capsize=4,
    )

    for i, comp in enumerate(comparison.outcome_comparisons):
        if comp["significant"]:
            max_rate = max(rates_a[i], rates_b[i])
            max_ci = max(ci_a[i], ci_b[i])
            ax.text(x[i], max_rate + max_ci + 0.02, "*", ha="center", fontsize=16, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(categories)
    ax.set_ylabel("Rate")
    ax.set_title(
        f"{comparison.run_a_name} vs {comparison.run_b_name}",
        fontsize=12, fontweight="bold",
    )
    ax.legend()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_ylim(bottom=0)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def plot_effect_sizes(
    comparison: CrossRunComparison, output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    metrics = []
    d_values = []
    interpretations = []
    for m in comparison.metric_comparisons:
        metrics.append(m["metric"])
        d_values.append(m["cohens_d"])
        interpretations.append(m["interpretation"])

    for key, val in comparison.effect_sizes.items():
        if key not in metrics and isinstance(val, dict):
            metrics.append(key)
            d_values.append(val.get("d", 0.0))
            interpretations.append(val.get("interpretation", "negligible"))

    if not metrics:
        fig, ax = plt.subplots()
        ax.set_title("No effect size data")
        fig.savefig(output_path, dpi=150)
        plt.close(fig)
        return output_path

    color_map = {
        "negligible": "#4CAF50",
        "small": "#FFC107",
        "medium": "#FF9800",
        "large": "#F44336",
        "very_large": "#B71C1C",
    }
    colors = [color_map.get(interp, "#607D8B") for interp in interpretations]

    fig, ax = plt.subplots(figsize=(8, max(3, len(metrics) * 0.8 + 1)))
    y = np.arange(len(metrics))
    ax.barh(y, d_values, color=colors, edgecolor="white", linewidth=0.5, height=0.6)

    for ref in [0.2, 0.5, 0.8]:
        ax.axvline(ref, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
        ax.axvline(-ref, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)

    ax.set_yticks(y)
    ax.set_yticklabels(metrics)
    ax.set_xlabel("Cohen's d")
    ax.set_title("Effect Sizes", fontsize=12, fontweight="bold")
    ax.axvline(0, color="black", linewidth=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    from matplotlib.patches import Patch
    legend_items = []
    for interp in ["negligible", "small", "medium", "large", "very_large"]:
        if interp in interpretations:
            legend_items.append(Patch(facecolor=color_map[interp], label=interp))
    if legend_items:
        ax.legend(handles=legend_items, loc="best", fontsize=8)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def plot_step_distributions(
    trajectories_a: list[Trajectory],
    trajectories_b: list[Trajectory],
    name_a: str,
    name_b: str,
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    steps_a = [t.outcome.final_step for t in trajectories_a if t.outcome]
    steps_b = [t.outcome.final_step for t in trajectories_b if t.outcome]

    fig, ax = plt.subplots(figsize=(8, 5))

    if steps_a or steps_b:
        all_steps = steps_a + steps_b
        bins = max(5, min(20, len(all_steps) // 2))

        if steps_a:
            ax.hist(steps_a, bins=bins, alpha=0.5, color="#2196F3", label=name_a, edgecolor="white")
            mean_a = sum(steps_a) / len(steps_a)
            ax.axvline(mean_a, color="#1565C0", linestyle="--", linewidth=2, label=f"{name_a} mean")

        if steps_b:
            ax.hist(steps_b, bins=bins, alpha=0.5, color="#F44336", label=name_b, edgecolor="white")
            mean_b = sum(steps_b) / len(steps_b)
            ax.axvline(mean_b, color="#B71C1C", linestyle="--", linewidth=2, label=f"{name_b} mean")

    ax.set_xlabel("Final Step")
    ax.set_ylabel("Count")
    ax.set_title("Step Count Distributions", fontsize=12, fontweight="bold")
    ax.legend()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def generate_comparison_plots(
    comparison: CrossRunComparison,
    trajectories_a: list[Trajectory],
    trajectories_b: list[Trajectory],
    output_path: Path,
) -> list[Path]:
    output_path.mkdir(parents=True, exist_ok=True)

    paths = [
        plot_outcome_comparison(comparison, output_path / "outcome_comparison.png"),
        plot_effect_sizes(comparison, output_path / "effect_sizes.png"),
        plot_step_distributions(
            trajectories_a, trajectories_b,
            comparison.run_a_name, comparison.run_b_name,
            output_path / "step_distributions.png",
        ),
    ]
    return paths


def _wilson_cis(rates: list[float], n: int) -> list[float]:
    if n <= 0:
        return [0.0] * len(rates)
    margins = []
    for p in rates:
        if n > 0:
            margins.append(1.96 * math.sqrt(p * (1 - p) / n))
        else:
            margins.append(0.0)
    return margins
