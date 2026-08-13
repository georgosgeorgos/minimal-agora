from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from worldsim.models import AggregateResult, Trajectory


def aggregate_outcomes(trajectories: list[Trajectory], question: str = "") -> AggregateResult:
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
    path = output_dir / "report.json"
    with open(path, "w") as f:
        f.write(result.model_dump_json(indent=2))

    text_path = output_dir / "report.txt"
    with open(text_path, "w") as f:
        f.write(format_report(result))

    return path


def load_trajectories(output_dir: Path) -> list[Trajectory]:
    trajectories = []
    for traj_dir in sorted(output_dir.glob("trajectory_*")):
        traj_file = traj_dir / "trajectory.json"
        if traj_file.exists():
            with open(traj_file) as f:
                trajectories.append(Trajectory.model_validate_json(f.read()))
    return trajectories
