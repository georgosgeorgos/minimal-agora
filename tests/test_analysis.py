import tempfile
from pathlib import Path

from minimal_agora.analysis import (
    compute_agent_calibration,
    compute_outcome_coverage,
    compute_statistics,
    extract_field_timelines,
    save_artifacts,
)
from minimal_agora.models import (
    Critique,
    Proposal,
    Resolution,
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


def _make_calibration_trajectory(
    tid: int,
    outcome: str,
    steps_data: list[dict],
) -> Trajectory:
    """Build a trajectory with proposals, critiques, and resolutions for calibration tests."""
    steps = []
    for item in steps_data:
        step = Step(
            step_number=item["step_number"],
            proposals=item.get("proposals", []),
            critiques=item.get("critiques", []),
            resolution=item.get("resolution"),
            state_before=item.get("state_before", {}),
            state_after=item.get("state_after", {}),
        )
        steps.append(step)
    return Trajectory(
        scenario_name="test",
        trajectory_id=tid,
        steps=steps,
        outcome=TrajectoryOutcome(
            classification=outcome,
            final_step=len(steps) - 1,
            final_state=steps_data[-1].get("state_after", {}) if steps_data else {},
        ),
    )


def test_compute_agent_calibration_basic():
    """Test calibration with two agents across two steps."""
    t = _make_calibration_trajectory(0, "success", [
        {
            "step_number": 0,
            "proposals": [
                Proposal(
                    agent="alice",
                    role="actor",
                    proposed_changes={"gdp": 100, "population": 50},
                    confidence=0.8,
                ),
                Proposal(
                    agent="bob",
                    role="actor",
                    proposed_changes={"gdp": 200},
                    confidence=0.6,
                ),
            ],
            "critiques": [
                Critique(
                    agent="evaluator",
                    target_proposals=["alice"],
                    plausibility=0.9,
                ),
            ],
            "resolution": Resolution(
                state_delta={"gdp": 100, "population": 45},
            ),
            "state_after": {"gdp": 100, "population": 45},
        },
        {
            "step_number": 1,
            "proposals": [
                Proposal(
                    agent="alice",
                    role="actor",
                    proposed_changes={"gdp": 150},
                    confidence=0.7,
                ),
                Proposal(
                    agent="bob",
                    role="actor",
                    proposed_changes={"gdp": 300},
                    confidence=0.9,
                ),
            ],
            "critiques": [],
            "resolution": Resolution(
                state_delta={"gdp": 300},
            ),
            "state_after": {"gdp": 300},
        },
    ])

    cal = compute_agent_calibration([t])

    # Alice: 2 proposals made. Step 0: gdp=100 accepted (matches delta). Step 1: gdp=150 not accepted (delta has 300).
    assert cal["alice"]["proposals_made"] == 2
    assert cal["alice"]["proposals_accepted"] == 1
    assert abs(cal["alice"]["acceptance_rate"] - 0.5) < 1e-9
    assert abs(cal["alice"]["mean_confidence"] - 0.75) < 1e-9  # (0.8 + 0.7) / 2
    assert abs(cal["alice"]["confidence_calibration"] - 0.25) < 1e-9  # |0.75 - 0.5|
    assert cal["alice"]["mean_plausibility"] == 0.9

    # Bob: 2 proposals made. Step 0: gdp=200 not accepted (delta has 100). Step 1: gdp=300 accepted.
    assert cal["bob"]["proposals_made"] == 2
    assert cal["bob"]["proposals_accepted"] == 1
    assert abs(cal["bob"]["acceptance_rate"] - 0.5) < 1e-9
    assert abs(cal["bob"]["mean_confidence"] - 0.75) < 1e-9  # (0.6 + 0.9) / 2
    assert cal["bob"]["mean_plausibility"] is None  # no critiques targeted bob


def test_compute_agent_calibration_empty():
    """No proposals => empty result."""
    t = _make_calibration_trajectory(0, "outcome", [
        {
            "step_number": 0,
            "state_after": {"x": 1},
        },
    ])
    cal = compute_agent_calibration([t])
    assert cal == {}


def test_compute_agent_calibration_float_tolerance():
    """Float values within 10% should count as accepted."""
    t = _make_calibration_trajectory(0, "outcome", [
        {
            "step_number": 0,
            "proposals": [
                Proposal(
                    agent="agent_a",
                    role="actor",
                    proposed_changes={"temperature": 100.0},
                    confidence=0.5,
                ),
            ],
            "resolution": Resolution(
                state_delta={"temperature": 105.0},  # 5% off -> within 10%
            ),
            "state_after": {"temperature": 105.0},
        },
        {
            "step_number": 1,
            "proposals": [
                Proposal(
                    agent="agent_a",
                    role="actor",
                    proposed_changes={"temperature": 100.0},
                    confidence=0.5,
                ),
            ],
            "resolution": Resolution(
                state_delta={"temperature": 115.0},  # 15% off -> outside 10%
            ),
            "state_after": {"temperature": 115.0},
        },
    ])
    cal = compute_agent_calibration([t])
    assert cal["agent_a"]["proposals_made"] == 2
    assert cal["agent_a"]["proposals_accepted"] == 1


def test_compute_agent_calibration_nested_changes():
    """Nested proposed_changes should be flattened to dot-paths."""
    t = _make_calibration_trajectory(0, "outcome", [
        {
            "step_number": 0,
            "proposals": [
                Proposal(
                    agent="agent_nested",
                    role="actor",
                    proposed_changes={"economy": {"gdp": 500}},
                    confidence=0.6,
                ),
            ],
            "resolution": Resolution(
                state_delta={"economy": {"gdp": 500}},
            ),
            "state_after": {"economy": {"gdp": 500}},
        },
    ])
    cal = compute_agent_calibration([t])
    assert cal["agent_nested"]["proposals_accepted"] == 1
    assert "economy.gdp" in cal["agent_nested"]["fields_proposed"]


def test_compute_agent_calibration_no_resolution():
    """Steps without a resolution should not count as accepted."""
    t = _make_calibration_trajectory(0, "outcome", [
        {
            "step_number": 0,
            "proposals": [
                Proposal(
                    agent="orphan",
                    role="actor",
                    proposed_changes={"x": 10},
                    confidence=0.9,
                ),
            ],
            "resolution": None,
            "state_after": {"x": 10},
        },
    ])
    cal = compute_agent_calibration([t])
    assert cal["orphan"]["proposals_made"] == 1
    assert cal["orphan"]["proposals_accepted"] == 0


# --- Outcome coverage tests ---


def test_outcome_coverage_single_trajectory():
    """Single trajectory: entropy should be 0, divergence should be 0."""
    t = _make_trajectory(0, "outcome_a", [{"x": 10, "y": 20}])
    metrics = compute_outcome_coverage([t])
    assert metrics["n_outcomes"] == 1
    assert metrics["outcome_entropy"] == 0.0
    assert metrics["normalized_entropy"] == 0.0
    assert metrics["trajectory_divergence"] == 0.0


def test_outcome_coverage_uniform():
    """Equal distribution across outcomes: entropy should be maximal."""
    import math

    trajectories = [
        _make_trajectory(0, "A", [{"x": 1}]),
        _make_trajectory(1, "B", [{"x": 2}]),
        _make_trajectory(2, "C", [{"x": 3}]),
        _make_trajectory(3, "D", [{"x": 4}]),
    ]
    metrics = compute_outcome_coverage(trajectories)
    assert metrics["n_outcomes"] == 4
    assert abs(metrics["outcome_entropy"] - math.log2(4)) < 1e-9
    assert abs(metrics["normalized_entropy"] - 1.0) < 1e-9


def test_outcome_coverage_identical_states():
    """All final states the same: divergence should be 0."""
    trajectories = [
        _make_trajectory(0, "A", [{"x": 5, "y": 10}]),
        _make_trajectory(1, "A", [{"x": 5, "y": 10}]),
        _make_trajectory(2, "A", [{"x": 5, "y": 10}]),
    ]
    metrics = compute_outcome_coverage(trajectories)
    assert metrics["trajectory_divergence"] == 0.0
    assert metrics["state_space_coverage"] == 0.0


def test_outcome_coverage_diverse_states():
    """Spread final states: divergence should be > 0."""
    trajectories = [
        _make_trajectory(0, "A", [{"x": 0, "y": 0}]),
        _make_trajectory(1, "B", [{"x": 100, "y": 100}]),
        _make_trajectory(2, "C", [{"x": 200, "y": 200}]),
    ]
    metrics = compute_outcome_coverage(trajectories)
    assert metrics["trajectory_divergence"] > 0
    assert metrics["state_space_coverage"] > 0
    assert metrics["n_outcomes"] == 3
