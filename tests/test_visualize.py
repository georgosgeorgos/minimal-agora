import tempfile
from pathlib import Path

from minimal_agora.models import (
    Critique,
    Proposal,
    Resolution,
    Step,
    Trajectory,
    TrajectoryOutcome,
)
from minimal_agora.visualize import (
    plot_agent_activity,
    plot_field_timelines,
    plot_outcome_distribution,
    plot_population_scores,
    plot_step_distribution,
    plot_trajectory_comparison,
    plot_wildcard_impact,
)


def _make_evolution_trajectory(tid: int, outcome: str, n_steps: int = 5) -> Trajectory:
    steps = []
    complexity = 10 + tid * 5
    oxygen = 5.0 + tid * 2
    for i in range(n_steps):
        complexity += (i + 1) * 3 + tid
        oxygen += 1.5 + tid * 0.5
        steps.append(Step(
            step_number=i,
            state_before={},
            state_after={
                "life": {"complexity": complexity, "intelligence": i == n_steps - 1 and outcome == "intelligent"},
                "environment": {"oxygen_level": oxygen, "biodiversity": "low" if i < 3 else "moderate"},
            },
        ))
    return Trajectory(
        scenario_name="test-evolution",
        trajectory_id=tid,
        steps=steps,
        outcome=TrajectoryOutcome(
            classification=outcome,
            final_step=n_steps - 1,
            final_state=steps[-1].state_after,
        ),
    )


def _make_population_trajectory(tid: int, outcome: str, n_steps: int = 8) -> Trajectory:
    steps = []
    rome_mil = 60
    greece_mil = 45
    persia_mil = 70
    for i in range(n_steps):
        rome_mil += 5 - tid
        greece_mil += 3 + tid
        persia_mil -= 2
        steps.append(Step(
            step_number=i,
            state_before={},
            state_after={
                "populations": {
                    "rome": {"military_strength": rome_mil, "economy": 50 + i * 2, "culture": 40 + i},
                    "greece": {"military_strength": greece_mil, "economy": 55 + i, "culture": 80 - i},
                    "persia": {"military_strength": persia_mil, "economy": 65 - i, "culture": 55},
                },
            },
        ))
    return Trajectory(
        scenario_name="test-mediterranean",
        trajectory_id=tid,
        steps=steps,
        outcome=TrajectoryOutcome(
            classification=outcome,
            final_step=n_steps - 1,
            final_state=steps[-1].state_after,
        ),
    )


def test_plot_outcome_distribution():
    trajectories = [
        _make_evolution_trajectory(0, "intelligent"),
        _make_evolution_trajectory(1, "intelligent"),
        _make_evolution_trajectory(2, "stagnation"),
        _make_evolution_trajectory(3, "extinction"),
        _make_evolution_trajectory(4, "intelligent"),
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "outcomes.png"
        result = plot_outcome_distribution(trajectories, path)
        assert result.exists()
        assert result.stat().st_size > 1000


def test_plot_field_timelines():
    trajectories = [
        _make_evolution_trajectory(0, "intelligent"),
        _make_evolution_trajectory(1, "stagnation"),
        _make_evolution_trajectory(2, "intelligent"),
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "timelines.png"
        result = plot_field_timelines(
            trajectories, ["life.complexity", "environment.oxygen_level"], path,
        )
        assert result.exists()
        assert result.stat().st_size > 1000


def test_plot_field_timelines_categorical():
    trajectories = [
        _make_evolution_trajectory(0, "intelligent"),
        _make_evolution_trajectory(1, "stagnation"),
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "categorical.png"
        result = plot_field_timelines(
            trajectories, ["environment.biodiversity"], path,
        )
        assert result.exists()


def test_plot_step_distribution():
    trajectories = [
        _make_evolution_trajectory(0, "intelligent", n_steps=8),
        _make_evolution_trajectory(1, "intelligent", n_steps=6),
        _make_evolution_trajectory(2, "stagnation", n_steps=10),
        _make_evolution_trajectory(3, "extinction", n_steps=3),
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "steps.png"
        result = plot_step_distribution(trajectories, path)
        assert result.exists()
        assert result.stat().st_size > 1000


def test_plot_population_scores():
    trajectories = [
        _make_population_trajectory(0, "roman_dominance"),
        _make_population_trajectory(1, "greek_dominance"),
        _make_population_trajectory(2, "balance_of_power"),
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "military.png"
        result = plot_population_scores(
            trajectories, ["rome", "greece", "persia"], "military_strength", path,
        )
        assert result.exists()
        assert result.stat().st_size > 1000


def _make_wildcard_trajectory(tid: int, outcome: str, n_steps: int = 6) -> Trajectory:
    steps = []
    val = 10.0 + tid * 5
    for i in range(n_steps):
        state_before = {"metric": val}
        if i in (2, 4):
            state_before["metric"] += 100
        val = state_before["metric"] + (i + 1) * 2
        state_after = {"metric": val}
        steps.append(Step(
            step_number=i,
            state_before=state_before,
            state_after=state_after,
        ))
    return Trajectory(
        scenario_name="test-wildcards",
        trajectory_id=tid,
        steps=steps,
        outcome=TrajectoryOutcome(
            classification=outcome,
            final_step=n_steps - 1,
            final_state=steps[-1].state_after,
        ),
    )


def _make_agent_trajectory(tid: int, outcome: str, n_steps: int = 5) -> Trajectory:
    steps = []
    for i in range(n_steps):
        proposals = [
            Proposal(agent="alice", role="actor", proposed_changes={"x": i}, confidence=0.8),
            Proposal(agent="bob", role="actor", proposed_changes={"y": i}, confidence=0.6),
        ]
        critiques = [
            Critique(agent="carol", target_proposals=["alice"], plausibility=0.7 + tid * 0.05),
            Critique(agent="carol", target_proposals=["bob"], plausibility=0.4 + tid * 0.1),
        ]
        resolution = Resolution(state_delta={"x": i + 1}, narrative="step resolved")
        steps.append(Step(
            step_number=i,
            proposals=proposals,
            critiques=critiques,
            resolution=resolution,
            state_before={"x": i, "y": i},
            state_after={"x": i + 1, "y": i},
        ))
    return Trajectory(
        scenario_name="test-agents",
        trajectory_id=tid,
        steps=steps,
        outcome=TrajectoryOutcome(
            classification=outcome,
            final_step=n_steps - 1,
            final_state=steps[-1].state_after,
        ),
    )


def test_plot_trajectory_comparison():
    trajectories = [
        _make_evolution_trajectory(0, "intelligent"),
        _make_evolution_trajectory(1, "stagnation"),
        _make_evolution_trajectory(2, "intelligent"),
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "comparison.png"
        result = plot_trajectory_comparison(
            trajectories, ["life.complexity", "environment.oxygen_level"], path,
        )
        assert result.exists()
        assert result.stat().st_size > 1000


def test_plot_trajectory_comparison_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "comparison.png"
        result = plot_trajectory_comparison([], ["life.complexity"], path)
        assert result == path


def test_plot_wildcard_impact():
    trajectories = [
        _make_wildcard_trajectory(0, "outcome_a"),
        _make_wildcard_trajectory(1, "outcome_b"),
        _make_wildcard_trajectory(2, "outcome_a"),
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "wildcards.png"
        result = plot_wildcard_impact(trajectories, path)
        assert result.exists()
        assert result.stat().st_size > 1000


def test_plot_wildcard_impact_no_events():
    trajectories = [_make_evolution_trajectory(0, "intelligent")]
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "wildcards.png"
        result = plot_wildcard_impact(trajectories, path)
        assert result.exists()


def test_plot_agent_activity():
    trajectories = [
        _make_agent_trajectory(0, "success"),
        _make_agent_trajectory(1, "failure"),
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "agents.png"
        result = plot_agent_activity(trajectories, path)
        assert result.exists()
        assert result.stat().st_size > 1000


def test_plot_agent_activity_no_proposals():
    trajectories = [_make_evolution_trajectory(0, "intelligent")]
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "agents.png"
        result = plot_agent_activity(trajectories, path)
        assert result.exists()


def test_generate_all_plots_with_synthetic_data():
    trajectories = [
        _make_evolution_trajectory(0, "intelligent"),
        _make_evolution_trajectory(1, "stagnation"),
        _make_evolution_trajectory(2, "intelligent"),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        for t in trajectories:
            traj_dir = output_dir / f"trajectory_{t.trajectory_id:03d}"
            traj_dir.mkdir(parents=True)
            with open(traj_dir / "trajectory.json", "w") as f:
                f.write(t.model_dump_json(indent=2))

        from minimal_agora.visualize import generate_all_plots
        paths = generate_all_plots(
            output_dir,
            fields=["life.complexity", "environment.oxygen_level"],
        )
        assert len(paths) >= 6
        assert all(p.exists() for p in paths)


def test_generate_all_plots_with_type_filter():
    trajectories = [
        _make_evolution_trajectory(0, "intelligent"),
        _make_evolution_trajectory(1, "stagnation"),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        for t in trajectories:
            traj_dir = output_dir / f"trajectory_{t.trajectory_id:03d}"
            traj_dir.mkdir(parents=True)
            with open(traj_dir / "trajectory.json", "w") as f:
                f.write(t.model_dump_json(indent=2))

        from minimal_agora.visualize import generate_all_plots
        paths = generate_all_plots(
            output_dir,
            plot_types=["outcomes", "wildcards"],
        )
        assert len(paths) == 2
        assert all(p.exists() for p in paths)
