from __future__ import annotations

import json
import logging

from structlog.testing import capture_logs

from minimal_agora.logging_config import configure_logging
from minimal_agora.models import Resolution, Trajectory, TrajectoryOutcome
from minimal_agora.scenario import load_scenario


def test_configure_logging_sets_level():
    configure_logging(verbose=False)
    assert logging.getLogger().level == logging.INFO

    configure_logging(verbose=True)
    assert logging.getLogger().level == logging.DEBUG


def test_scenario_load_emits_log_events():
    with capture_logs() as cap:
        load_scenario("scenarios/examples/intelligence.yaml")

    events = [e["event"] for e in cap]
    assert "scenario.load" in events
    assert "scenario.loaded" in events

    loaded = next(e for e in cap if e["event"] == "scenario.loaded")
    assert "name" in loaded
    assert "mode" in loaded


def test_aggregate_outcomes_emits_log_events():
    from minimal_agora.analysis import aggregate_outcomes

    trajectories = [
        Trajectory(
            scenario_name="test",
            trajectory_id=i,
            outcome=TrajectoryOutcome(classification="a", final_step=3, final_state={}),
        )
        for i in range(3)
    ]

    with capture_logs() as cap:
        aggregate_outcomes(trajectories, "q")

    events = [e["event"] for e in cap]
    assert "analysis.aggregate_outcomes" in events
    assert "analysis.aggregate_outcomes.done" in events


def test_board_apply_resolution_emits_log_events(tmp_path):
    from minimal_agora.board import Board

    workspace = tmp_path / "ws"
    board_dir = workspace / "board"
    board_dir.mkdir(parents=True)
    (workspace / "history").mkdir()

    with open(board_dir / "state.json", "w") as f:
        json.dump({"x": 1}, f)

    with open(board_dir / "narrative.md", "w") as f:
        f.write("# Narrative\n")

    board = Board(workspace)
    resolution = Resolution(state_delta={"x": 2}, narrative="update", reasoning="test")

    with capture_logs() as cap:
        board.apply_resolution(resolution, step=0)

    events = [e["event"] for e in cap]
    assert "board.apply_resolution" in events
    assert "board.snapshot_state" in events
