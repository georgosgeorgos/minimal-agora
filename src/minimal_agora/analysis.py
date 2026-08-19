from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from minimal_agora.logging import get_logger
from minimal_agora.models import AggregateResult, Trajectory

logger = get_logger(__name__)


def aggregate_outcomes(trajectories: list[Trajectory], question: str = "") -> AggregateResult:
    logger.info("aggregate_outcomes", n_trajectories=len(trajectories))
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

    return AggregateResult(
        scenario_name=scenario_name,
        question=question,
        n_trajectories=n,
        outcomes=dict(counts),
        outcome_rates=rates,
        mean_steps_per_outcome=mean_steps,
    )


def extract_field_timelines(
    trajectories: list[Trajectory], fields: list[str],
) -> dict[str, dict[int, list]]:
    logger.debug("extract_field_timelines", fields=fields, n_trajectories=len(trajectories))
    timelines: dict[str, dict[int, list]] = {f: defaultdict(list) for f in fields}
    for t in trajectories:
        for step in t.steps:
            for field in fields:
                val = _get_nested(step.state_after, field)
                if val is not None:
                    timelines[field][step.step_number].append(val)
    return timelines


def compute_statistics(values: Sequence[float | int]) -> dict[str, float]:
    logger.debug("compute_statistics", n_values=len(values))
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
    logger.debug("format_report", scenario=result.scenario_name)
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
    output_dir.mkdir(parents=True, exist_ok=True)

    path = output_dir / "report.json"
    with open(path, "w") as f:
        f.write(result.model_dump_json(indent=2))

    text_path = output_dir / "report.txt"
    with open(text_path, "w") as f:
        f.write(format_report(result))

    return path


def save_artifacts(trajectories: list[Trajectory], output_dir: Path) -> Path:
    logger.info("save_artifacts", output_dir=str(output_dir), n_trajectories=len(trajectories))
    artifacts_dir = output_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    traj_summaries: list[dict[str, object]] = []

    for t in trajectories:
        traj_summary: dict[str, object] = {
            "id": t.trajectory_id,
            "n_steps": len(t.steps),
            "outcome": t.outcome.classification if t.outcome else "unclassified",
            "final_step": t.outcome.final_step if t.outcome else len(t.steps) - 1,
        }
        traj_summaries.append(traj_summary)

    summary: dict[str, object] = {
        "scenario": trajectories[0].scenario_name if trajectories else "unknown",
        "n_trajectories": len(trajectories),
        "trajectories": traj_summaries,
    }

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


def _get_nested(d: dict, path: str):
    keys = path.split(".")
    current = d
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current
