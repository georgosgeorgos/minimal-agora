import tempfile
from pathlib import Path

from minimal_agora.models import (
    CrossRunComparison,
    Step,
    Trajectory,
    TrajectoryOutcome,
)
from minimal_agora.visualize_comparison import (
    generate_comparison_plots,
    plot_effect_sizes,
    plot_outcome_comparison,
    plot_step_distributions,
)

PNG_MAGIC = b"\x89PNG"


def _make_trajectories(
    name: str, outcomes: list[tuple[str, int]],
) -> list[Trajectory]:
    trajs = []
    for i, (cls, final_step) in enumerate(outcomes):
        steps = [
            Step(step_number=s, state_before={}, state_after={})
            for s in range(final_step + 1)
        ]
        trajs.append(Trajectory(
            scenario_name=name,
            trajectory_id=i,
            steps=steps,
            outcome=TrajectoryOutcome(
                classification=cls, final_step=final_step, final_state={},
            ),
        ))
    return trajs


def _make_comparison() -> CrossRunComparison:
    return CrossRunComparison(
        run_a_name="baseline",
        run_b_name="experiment",
        n_trajectories_a=10,
        n_trajectories_b=10,
        outcome_comparisons=[
            {
                "category": "success",
                "rate_a": 0.7,
                "rate_b": 0.4,
                "z_stat": 1.34,
                "p_value": 0.03,
                "significant": True,
            },
            {
                "category": "failure",
                "rate_a": 0.2,
                "rate_b": 0.5,
                "z_stat": -1.41,
                "p_value": 0.16,
                "significant": False,
            },
            {
                "category": "timeout",
                "rate_a": 0.1,
                "rate_b": 0.1,
                "z_stat": 0.0,
                "p_value": 1.0,
                "significant": False,
            },
        ],
        metric_comparisons=[
            {
                "metric": "final_step",
                "mean_a": 12.3,
                "mean_b": 8.7,
                "cohens_d": 0.65,
                "interpretation": "medium",
            },
        ],
        effect_sizes={
            "final_step": {"d": 0.65, "interpretation": "medium"},
        },
        summary="Found 1 significant difference.",
    )


def test_plot_outcome_comparison():
    comparison = _make_comparison()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "outcome_comparison.png"
        result = plot_outcome_comparison(comparison, path)
        assert result.exists()
        assert result.stat().st_size > 1000
        with open(result, "rb") as f:
            assert f.read(4) == PNG_MAGIC


def test_plot_effect_sizes():
    comparison = _make_comparison()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "effect_sizes.png"
        result = plot_effect_sizes(comparison, path)
        assert result.exists()
        assert result.stat().st_size > 1000
        with open(result, "rb") as f:
            assert f.read(4) == PNG_MAGIC


def test_plot_step_distributions():
    traj_a = _make_trajectories("run_a", [
        ("success", 10), ("success", 12), ("failure", 8),
        ("success", 15), ("timeout", 20),
    ])
    traj_b = _make_trajectories("run_b", [
        ("success", 7), ("failure", 5), ("failure", 9),
        ("success", 6), ("success", 8),
    ])
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "step_distributions.png"
        result = plot_step_distributions(traj_a, traj_b, "run_a", "run_b", path)
        assert result.exists()
        assert result.stat().st_size > 1000
        with open(result, "rb") as f:
            assert f.read(4) == PNG_MAGIC


def test_generate_comparison_plots():
    comparison = _make_comparison()
    traj_a = _make_trajectories("baseline", [
        ("success", 10), ("success", 14), ("failure", 8),
    ])
    traj_b = _make_trajectories("experiment", [
        ("success", 7), ("failure", 5), ("success", 9),
    ])
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "plots"
        paths = generate_comparison_plots(comparison, traj_a, traj_b, output_path)
        assert len(paths) == 3
        for p in paths:
            assert p.exists()
            assert p.stat().st_size > 1000
            with open(p, "rb") as f:
                assert f.read(4) == PNG_MAGIC
