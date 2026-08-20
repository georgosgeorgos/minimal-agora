from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from minimal_agora.board import Board, _atomic_write
from minimal_agora.models import (
    AgentRole,
    Proposal,
    Resolution,
    Scenario,
    SimMode,
    Step,
)


def test_atomic_write_produces_correct_content(tmp_path: Path):
    target = tmp_path / "output.json"
    data = {"key": "value", "nested": {"a": 1}}
    with _atomic_write(target) as f:
        json.dump(data, f, indent=2)
    assert target.exists()
    with open(target) as f:
        assert json.load(f) == data


def test_atomic_write_interrupted_leaves_original_intact(tmp_path: Path):
    target = tmp_path / "state.json"
    original = {"version": 1}
    with open(target, "w") as f:
        json.dump(original, f)

    try:
        with _atomic_write(target) as f:
            f.write('{"version": 2, "partial":')
            raise RuntimeError("simulated crash")
    except RuntimeError:
        pass

    with open(target) as f:
        assert json.load(f) == original


def test_atomic_write_no_temp_files_after_success(tmp_path: Path):
    target = tmp_path / "data.json"
    with _atomic_write(target) as f:
        json.dump({"ok": True}, f)

    remaining = list(tmp_path.glob(".tmp_*"))
    assert remaining == []


def test_atomic_write_no_temp_files_after_failure(tmp_path: Path):
    target = tmp_path / "data.json"
    try:
        with _atomic_write(target) as f:
            f.write("bad")
            raise ValueError("boom")
    except ValueError:
        pass

    remaining = list(tmp_path.glob(".tmp_*"))
    assert remaining == []


def test_board_write_state_uses_atomic(tmp_path: Path):
    workspace = tmp_path / "ws"
    board_dir = workspace / "board"
    board_dir.mkdir(parents=True)
    (workspace / "history").mkdir()
    with open(board_dir / "state.json", "w") as f:
        json.dump({"x": 0}, f)

    board = Board(workspace)
    board.write_state({"x": 42})

    with open(board_dir / "state.json") as f:
        assert json.load(f) == {"x": 42}
    assert list(board_dir.glob(".tmp_*")) == []


def test_board_save_step_uses_atomic(tmp_path: Path):
    workspace = tmp_path / "ws"
    (workspace / "history").mkdir(parents=True)
    board = Board(workspace)

    step = Step(step_number=0, state_before={"a": 1}, state_after={"a": 2})
    path = board.save_step(step)
    assert path.exists()
    loaded = Step.model_validate_json(path.read_text())
    assert loaded.step_number == 0
    assert list((workspace / "history").glob(".tmp_*")) == []


def test_board_save_proposal_uses_atomic(tmp_path: Path):
    workspace = tmp_path / "ws"
    (workspace / "proposals").mkdir(parents=True)
    board = Board(workspace)

    p = Proposal(agent="a", role=AgentRole.ACTOR, proposed_changes={"x": 1})
    path = board.save_proposal(p, step=0)
    assert path.exists()
    assert list((workspace / "proposals").glob(".tmp_*")) == []


def test_board_save_resolution_uses_atomic(tmp_path: Path):
    workspace = tmp_path / "ws"
    (workspace / "resolutions").mkdir(parents=True)
    board = Board(workspace)

    r = Resolution(state_delta={"x": 1}, narrative="n", reasoning="r")
    path = board.save_resolution(r, step=0)
    assert path.exists()
    assert list((workspace / "resolutions").glob(".tmp_*")) == []


def test_resume_metadata_populated():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        (workspace / "board").mkdir(parents=True)
        (workspace / "history").mkdir()
        (workspace / "proposals").mkdir()
        (workspace / "critiques").mkdir()
        (workspace / "resolutions").mkdir()

        with open(workspace / "board" / "state.json", "w") as f:
            json.dump({"x": 0}, f)
        with open(workspace / "board" / "narrative.md", "w") as f:
            f.write("# Narrative\n")

        for i in range(3):
            step = Step(step_number=i, state_before={"x": i}, state_after={"x": i + 1})
            with open(workspace / "history" / f"step_{i:03d}_full.json", "w") as f:
                f.write(step.model_dump_json())

        state_at_3 = {"x": 3}
        with open(workspace / "history" / "step_003_state.json", "w") as f:
            json.dump(state_at_3, f)

        scenario = Scenario(
            name="test",
            mode=SimMode.COUNTERFACTUAL,
            initial_state={"x": 0},
            step_budget=3,
            termination={"max_steps": 3},
        )

        result = asyncio.run(
            __import__("minimal_agora.loop", fromlist=["run_trajectory"]).run_trajectory(
                scenario, workspace, trajectory_id=0,
            )
        )

        assert result.metadata.get("resumed") is True
        assert result.metadata.get("resume_from_step") == 3
        assert "resume_timestamp" in result.metadata
