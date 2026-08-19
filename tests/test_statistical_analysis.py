from __future__ import annotations

from pathlib import Path

from minimal_agora.analysis import (
    cohens_d,
    compare_outcome_proportions,
    compare_runs,
    outcome_rate_with_ci,
)
from minimal_agora.models import (
    Step,
    Trajectory,
    TrajectoryOutcome,
)


def _make_trajectory(tid: int, outcome: str, n_steps: int = 3) -> Trajectory:
    steps = [
        Step(step_number=i, state_before={}, state_after={"x": i})
        for i in range(n_steps)
    ]
    return Trajectory(
        scenario_name="test",
        trajectory_id=tid,
        steps=steps,
        outcome=TrajectoryOutcome(
            classification=outcome,
            final_step=n_steps - 1,
            final_state={"x": n_steps - 1},
        ),
    )


def test_cohens_d_well_separated():
    group_a = [10.0, 11.0, 10.5, 10.2, 10.8]
    group_b = [1.0, 1.5, 1.2, 0.8, 1.1]
    result = cohens_d(group_a, group_b)
    assert result["d"] > 1.5
    assert result["interpretation"] == "very_large"


def test_cohens_d_identical():
    group = [5.0, 5.0, 5.0, 5.0]
    result = cohens_d(group, group)
    assert result["d"] == 0.0
    assert result["interpretation"] == "negligible"


def test_cohens_d_small_groups():
    result = cohens_d([1.0], [2.0])
    assert result["d"] == 0.0
    assert result["interpretation"] == "negligible"


def test_compare_outcome_proportions_significant():
    result = compare_outcome_proportions(
        count_a=90, nobs_a=100,
        count_b=10, nobs_b=100,
    )
    assert result["significant"] is True
    assert result["p_value"] < 0.05
    assert isinstance(result["z_stat"], float)


def test_compare_outcome_proportions_not_significant():
    result = compare_outcome_proportions(
        count_a=50, nobs_a=100,
        count_b=48, nobs_b=100,
    )
    assert result["significant"] is False
    assert result["p_value"] > 0.05


def test_outcome_rate_with_ci():
    trajectories = (
        [_make_trajectory(i, "A") for i in range(7)]
        + [_make_trajectory(i + 7, "B") for i in range(3)]
    )
    result = outcome_rate_with_ci(trajectories, "A")
    assert result["rate"] == 0.7
    assert result["ci_lower"] <= result["rate"]
    assert result["ci_upper"] >= result["rate"]
    assert 0.0 <= result["ci_lower"]
    assert result["ci_upper"] <= 1.0


def test_outcome_rate_with_ci_single():
    trajectories = [_make_trajectory(0, "A")]
    result = outcome_rate_with_ci(trajectories, "A")
    assert result["rate"] == 1.0
    assert result["ci_lower"] == 1.0
    assert result["ci_upper"] == 1.0


def test_compare_runs_integration():
    traj_a = [_make_trajectory(i, "win", n_steps=5) for i in range(8)] + [
        _make_trajectory(i + 8, "lose", n_steps=3) for i in range(2)
    ]
    traj_b = [_make_trajectory(i, "win", n_steps=3) for i in range(3)] + [
        _make_trajectory(i + 3, "lose", n_steps=5) for i in range(7)
    ]

    result = compare_runs(traj_a, traj_b, name_a="exp_a", name_b="exp_b")

    assert result.run_a_name == "exp_a"
    assert result.run_b_name == "exp_b"
    assert result.n_trajectories_a == 10
    assert result.n_trajectories_b == 10
    assert len(result.outcome_comparisons) == 2

    win_comp = next(c for c in result.outcome_comparisons if c["category"] == "win")
    assert win_comp["rate_a"] == 0.8
    assert win_comp["rate_b"] == 0.3
    assert win_comp["significant"] is True

    assert result.summary
    assert "significant" in result.summary.lower()


def test_compare_runs_no_difference():
    traj_a = [_make_trajectory(i, "draw", n_steps=4) for i in range(5)]
    traj_b = [_make_trajectory(i, "draw", n_steps=4) for i in range(5)]

    result = compare_runs(traj_a, traj_b)
    assert result.n_trajectories_a == 5
    assert result.n_trajectories_b == 5

    for c in result.outcome_comparisons:
        assert c["significant"] is False

    assert "no significant" in result.summary.lower()


def test_compare_cli_subcommand(tmp_path: Path):
    dir_a = tmp_path / "run_a"
    dir_b = tmp_path / "run_b"

    for i, (d, outcome) in enumerate([
        (dir_a, "win"), (dir_a, "win"), (dir_a, "lose"),
        (dir_b, "lose"), (dir_b, "lose"), (dir_b, "win"),
    ]):
        traj_dir = d / f"trajectory_{i:03d}"
        traj_dir.mkdir(parents=True, exist_ok=True)
        t = _make_trajectory(i, outcome)
        (traj_dir / "trajectory.json").write_text(t.model_dump_json())

    import sys

    from minimal_agora.cli import main

    orig = sys.argv
    sys.argv = ["minimal-agora", "compare", str(dir_a), str(dir_b), "--format", "json"]
    try:
        code = main()
    finally:
        sys.argv = orig

    assert code == 0
