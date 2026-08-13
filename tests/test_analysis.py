import tempfile
from pathlib import Path

from minimal_agora.analysis import (
    compute_statistics,
    extract_field_timelines,
    save_artifacts,
)
from minimal_agora.models import (
    Step,
    Trajectory,
    TrajectoryOutcome,
)


def _make_trajectory(tid: int, outcome: str, steps_data: list[dict]) -> Trajectory:
    steps = []
    for i, state in enumerate(steps_data):
        steps.append(Step(
            step_number=i,
            state_before=steps_data[i - 1] if i > 0 else {},
            state_after=state,
        ))
    return Trajectory(
        scenario_name="test",
        trajectory_id=tid,
        steps=steps,
        outcome=TrajectoryOutcome(
            classification=outcome,
            final_step=len(steps) - 1,
            final_state=steps_data[-1] if steps_data else {},
        ),
    )


def test_compute_statistics():
    stats = compute_statistics([1, 2, 3, 4, 5])
    assert stats["mean"] == 3.0
    assert stats["min"] == 1
    assert stats["max"] == 5
    assert stats["median"] == 3
    assert stats["n"] == 5
    assert abs(stats["std"] - 1.5811) < 0.001


def test_compute_statistics_empty():
    assert compute_statistics([]) == {}


def test_compute_statistics_single():
    stats = compute_statistics([42.0])
    assert stats["mean"] == 42.0
    assert stats["std"] == 0.0
    assert stats["median"] == 42.0


def test_extract_field_timelines():
    t1 = _make_trajectory(0, "A", [
        {"life": {"complexity": 10}},
        {"life": {"complexity": 20}},
        {"life": {"complexity": 30}},
    ])
    t2 = _make_trajectory(1, "B", [
        {"life": {"complexity": 15}},
        {"life": {"complexity": 25}},
        {"life": {"complexity": 35}},
    ])

    timelines = extract_field_timelines([t1, t2], ["life.complexity"])
    data = timelines["life.complexity"]
    assert data[0] == [10, 15]
    assert data[1] == [20, 25]
    assert data[2] == [30, 35]


def test_save_artifacts():
    trajectories = [
        _make_trajectory(0, "A", [{"x": 1}, {"x": 2}]),
        _make_trajectory(1, "B", [{"x": 3}, {"x": 4}]),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        artifacts_dir = save_artifacts(trajectories, output_dir)
        assert (artifacts_dir / "summary.json").exists()
        assert (artifacts_dir / "final_states.json").exists()

        import json
        with open(artifacts_dir / "summary.json") as f:
            summary = json.load(f)
        assert summary["n_trajectories"] == 2
        assert len(summary["trajectories"]) == 2
        assert summary["trajectories"][0]["outcome"] == "A"
