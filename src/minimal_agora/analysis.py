from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import structlog
from scipy import stats as scipy_stats  # type: ignore[import-untyped]
from statsmodels.stats.proportion import proportions_ztest  # type: ignore[import-untyped]

from minimal_agora.models import AggregateResult, CrossRunComparison, Trajectory

logger = structlog.stdlib.get_logger(__name__)


def aggregate_outcomes(trajectories: list[Trajectory], question: str = "") -> AggregateResult:
    logger.info("analysis.aggregate_outcomes", n_trajectories=len(trajectories))
    counts: dict[str, int] = defaultdict(int)
    steps_per_outcome: dict[str, list[int]] = defaultdict(list)

    scenario_name = trajectories[0].scenario_name if trajectories else "unknown"

    for t in trajectories:
        if t.outcome is None:
            counts["unclassified"] += 1
            continue
        cls = t.outcome.classification
        counts[cls] += 1
        steps_per_outcome[cls].append(t.outcome.final_step)

    n = len(trajectories)
    rates = {k: v / n for k, v in counts.items()} if n > 0 else {}
    mean_steps = {
        k: sum(v) / len(v) for k, v in steps_per_outcome.items() if v
    }

    outcome_rates_ci: dict[str, tuple[float, float]] | None = None
    monte_carlo_se: dict[str, float] | None = None

    if n > 0:
        cis: dict[str, tuple[float, float]] = {}
        ses: dict[str, float] = {}
        for category, count in counts.items():
            ci = outcome_rate_with_ci(trajectories, category)
            cis[category] = (ci["ci_lower"], ci["ci_upper"])
            p = count / n
            ses[category] = math.sqrt(p * (1 - p) / n) if n > 1 else 0.0
        outcome_rates_ci = cis
        monte_carlo_se = ses

    result = AggregateResult(
        scenario_name=scenario_name,
        question=question,
        n_trajectories=n,
        outcomes=dict(counts),
        outcome_rates=rates,
        mean_steps_per_outcome=mean_steps,
        outcome_rates_ci=outcome_rates_ci,
        monte_carlo_se=monte_carlo_se,
    )
    logger.info("analysis.aggregate_outcomes.done", outcomes=dict(counts))
    return result


def extract_field_timelines(
    trajectories: list[Trajectory], fields: list[str],
) -> dict[str, dict[int, list]]:
    timelines: dict[str, dict[int, list]] = {f: defaultdict(list) for f in fields}
    for t in trajectories:
        for step in t.steps:
            for field in fields:
                val = _get_nested(step.state_after, field)
                if val is not None:
                    timelines[field][step.step_number].append(val)
    return timelines


def compute_statistics(values: Sequence[float | int]) -> dict[str, float]:
    logger.debug("analysis.compute_statistics", n_values=len(values))
    if not values:
        return {}
    n = len(values)
    mean = sum(values) / n
    if n > 1:
        variance = sum((x - mean) ** 2 for x in values) / (n - 1)
        std = math.sqrt(variance)
    else:
        variance = 0.0
        std = 0.0
    sorted_vals = sorted(values)
    median = sorted_vals[n // 2] if n % 2 else (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
    return {
        "mean": mean,
        "std": std,
        "min": min(values),
        "max": max(values),
        "median": median,
        "n": n,
    }


def format_report(result: AggregateResult) -> str:
    lines = [
        f"=== {result.scenario_name} ===",
        f"Question: {result.question}",
        f"Trajectories: {result.n_trajectories}",
        "",
        "Outcomes:",
    ]

    for name, count in sorted(result.outcomes.items(), key=lambda x: -x[1]):
        rate = result.outcome_rates.get(name, 0)
        mean_s = result.mean_steps_per_outcome.get(name)
        step_info = f"  mean steps: {mean_s:.1f}" if mean_s is not None else ""
        lines.append(f"  {name}: {count}/{result.n_trajectories} ({rate:.1%}){step_info}")

    return "\n".join(lines)


def save_report(result: AggregateResult, output_dir: Path) -> Path:
    logger.info("analysis.save_report", output_dir=str(output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)

    path = output_dir / "report.json"
    with open(path, "w") as f:
        f.write(result.model_dump_json(indent=2))

    text_path = output_dir / "report.txt"
    with open(text_path, "w") as f:
        f.write(format_report(result))

    return path


def save_artifacts(trajectories: list[Trajectory], output_dir: Path) -> Path:
    artifacts_dir = output_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "scenario": trajectories[0].scenario_name if trajectories else "unknown",
        "n_trajectories": len(trajectories),
        "trajectories": [],
    }

    for t in trajectories:
        traj_summary = {
            "id": t.trajectory_id,
            "n_steps": len(t.steps),
            "outcome": t.outcome.classification if t.outcome else "unclassified",
            "final_step": t.outcome.final_step if t.outcome else len(t.steps) - 1,
        }
        summary["trajectories"].append(traj_summary)

    with open(artifacts_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    all_final_states = {}
    for t in trajectories:
        if t.outcome and t.outcome.final_state:
            all_final_states[f"trajectory_{t.trajectory_id:03d}"] = t.outcome.final_state

    with open(artifacts_dir / "final_states.json", "w") as f:
        json.dump(all_final_states, f, indent=2)

    return artifacts_dir


def load_trajectories(output_dir: Path) -> list[Trajectory]:
    logger.info("analysis.load_trajectories", output_dir=str(output_dir))
    trajectories = []
    for traj_dir in sorted(output_dir.glob("trajectory_*")):
        traj_file = traj_dir / "trajectory.json"
        if traj_file.exists():
            with open(traj_file) as f:
                trajectories.append(Trajectory.model_validate_json(f.read()))
    return trajectories


def detect_convergence(
    trajectories: list[Trajectory], threshold: float = 0.8,
) -> list[str]:
    if len(trajectories) < 3:
        return []

    logger.debug("analysis.detect_convergence", n_trajectories=len(trajectories), threshold=threshold)
    warnings = []
    counts: dict[str, int] = defaultdict(int)
    n = len(trajectories)

    for t in trajectories:
        cls = t.outcome.classification if t.outcome else "unclassified"
        counts[cls] += 1

    for outcome, count in counts.items():
        rate = count / n
        if rate >= threshold:
            warnings.append(
                f"Possible mode collapse: {count}/{n} ({rate:.0%}) trajectories "
                f"classified as '{outcome}'. Consider increasing prompt diversity "
                f"or adding wildcard events."
            )

    return warnings


def compare_outcome_proportions(
    count_a: int,
    nobs_a: int,
    count_b: int,
    nobs_b: int,
    alpha: float = 0.05,
) -> dict[str, Any]:
    z_stat, p_value = proportions_ztest(
        count=np.array([count_a, count_b]),
        nobs=np.array([nobs_a, nobs_b]),
    )
    return {
        "z_stat": float(z_stat),
        "p_value": float(p_value),
        "significant": bool(p_value < alpha),
    }


def outcome_rate_with_ci(
    trajectories: list[Trajectory],
    category: str,
    confidence: float = 0.95,
    n_bootstrap: int = 9999,
) -> dict[str, float]:
    hits = np.array([
        1.0 if (t.outcome and t.outcome.classification == category) else 0.0
        for t in trajectories
    ])
    point_estimate = float(hits.mean())

    if len(hits) < 2:
        return {
            "rate": point_estimate,
            "ci_lower": point_estimate,
            "ci_upper": point_estimate,
        }

    result = scipy_stats.bootstrap(
        (hits,),
        np.mean,
        confidence_level=confidence,
        n_resamples=n_bootstrap,
        random_state=42,
    )
    return {
        "rate": point_estimate,
        "ci_lower": float(result.confidence_interval.low),
        "ci_upper": float(result.confidence_interval.high),
    }


def _interpret_cohens_d(d: float) -> str:
    d_abs = abs(d)
    if d_abs < 0.2:
        return "negligible"
    elif d_abs < 0.5:
        return "small"
    elif d_abs < 0.8:
        return "medium"
    elif d_abs < 1.2:
        return "large"
    return "very_large"


def cohens_d(
    group_a: Sequence[float],
    group_b: Sequence[float],
) -> dict[str, Any]:
    a = np.asarray(group_a, dtype=float)
    b = np.asarray(group_b, dtype=float)

    n_a, n_b = len(a), len(b)
    if n_a < 2 or n_b < 2:
        return {"d": 0.0, "interpretation": "negligible"}

    mean_a, mean_b = float(a.mean()), float(b.mean())
    var_a = float(a.var(ddof=1))
    var_b = float(b.var(ddof=1))

    pooled_std = math.sqrt(((n_a - 1) * var_a + (n_b - 1) * var_b) / (n_a + n_b - 2))

    if pooled_std == 0:
        d_val = 0.0
    else:
        d_val = (mean_a - mean_b) / pooled_std

    interpretation = _interpret_cohens_d(d_val)
    logger.debug("analysis.cohens_d", effect_size=d_val, interpretation=interpretation)
    return {"d": d_val, "interpretation": interpretation}


def compare_runs(
    trajectories_a: list[Trajectory],
    trajectories_b: list[Trajectory],
    name_a: str = "run_a",
    name_b: str = "run_b",
    alpha: float = 0.05,
) -> CrossRunComparison:
    n_a = len(trajectories_a)
    n_b = len(trajectories_b)
    logger.info(
        "analysis.compare_runs",
        run_a=name_a,
        run_b=name_b,
        n_trajectories_a=n_a,
        n_trajectories_b=n_b,
    )

    counts_a: dict[str, int] = defaultdict(int)
    counts_b: dict[str, int] = defaultdict(int)
    for t in trajectories_a:
        cls = t.outcome.classification if t.outcome else "unclassified"
        counts_a[cls] += 1
    for t in trajectories_b:
        cls = t.outcome.classification if t.outcome else "unclassified"
        counts_b[cls] += 1

    all_categories = sorted(set(counts_a) | set(counts_b))

    outcome_comparisons = []
    for cat in all_categories:
        ca, cb = counts_a.get(cat, 0), counts_b.get(cat, 0)
        rate_a = ca / n_a if n_a > 0 else 0.0
        rate_b = cb / n_b if n_b > 0 else 0.0

        if n_a > 0 and n_b > 0 and (ca + cb) > 0:
            ztest = compare_outcome_proportions(ca, n_a, cb, n_b, alpha=alpha)
        else:
            ztest = {"z_stat": 0.0, "p_value": 1.0, "significant": False}

        outcome_comparisons.append({
            "category": cat,
            "rate_a": rate_a,
            "rate_b": rate_b,
            "z_stat": ztest["z_stat"],
            "p_value": ztest["p_value"],
            "significant": ztest["significant"],
        })

    steps_a = [
        float(t.outcome.final_step) for t in trajectories_a if t.outcome
    ]
    steps_b = [
        float(t.outcome.final_step) for t in trajectories_b if t.outcome
    ]

    effect_sizes: dict[str, Any] = {}
    metric_comparisons: list[dict[str, Any]] = []
    if steps_a and steps_b:
        d_result = cohens_d(steps_a, steps_b)
        effect_sizes["final_step"] = d_result
        metric_comparisons.append({
            "metric": "final_step",
            "mean_a": float(np.mean(steps_a)),
            "mean_b": float(np.mean(steps_b)),
            "cohens_d": d_result["d"],
            "interpretation": d_result["interpretation"],
        })

    sig_diffs = [c for c in outcome_comparisons if c["significant"]]
    if sig_diffs:
        summary = (
            f"Found {len(sig_diffs)} significant outcome difference(s) "
            f"between {name_a} (n={n_a}) and {name_b} (n={n_b}) at alpha={alpha}."
        )
    else:
        summary = (
            f"No significant outcome differences between "
            f"{name_a} (n={n_a}) and {name_b} (n={n_b}) at alpha={alpha}."
        )

    logger.info("analysis.compare_runs.done", n_significant_differences=len(sig_diffs))
    return CrossRunComparison(
        run_a_name=name_a,
        run_b_name=name_b,
        n_trajectories_a=n_a,
        n_trajectories_b=n_b,
        outcome_comparisons=outcome_comparisons,
        metric_comparisons=metric_comparisons,
        effect_sizes=effect_sizes,
        summary=summary,
    )


def _get_nested(d: dict, path: str):
    keys = path.split(".")
    current = d
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current
