"""Integration coverage for particle lineage across resampling."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from minimal_agora import resampling, runner
from minimal_agora.analysis import load_trajectories
from minimal_agora.models import BoardAccessMode, ResamplingConfig, Scenario, SimMode, Step


def test_resampled_trajectory_history_matches_copied_workspace(monkeypatch, tmp_path: Path):
    scenario = Scenario(
        name="particle-lineage",
        mode=SimMode.COUNTERFACTUAL,
        n_trajectories=3,
        step_budget=3,
        initial_state={"origin": -1, "step": 0},
        resampling=ResamplingConfig(interval=2, min_particles=2, ess_threshold=0.9),
        board_access=BoardAccessMode.FILES,
    )

    async def fake_step(scenario, board, step_num, timeout, *, trajectory_id, **kwargs):
        before = board.read_state()
        after = {
            "origin": trajectory_id if step_num == 0 else before["origin"],
            "step": step_num + 1,
        }
        board.write_state(after)
        board.snapshot_state(step_num + 1)
        step = Step(step_number=step_num, state_before=before, state_after=after)
        board.save_step(step)
        return step

    critic_calls = []

    async def fake_invoke(agent, workspace, step, prompt, timeout):
        idx = int(workspace.name.rsplit("_", 1)[1])
        critic_calls.append((idx, step))
        score = [9, 1, 0][idx]
        (workspace / "critiques" / f"resample_step_{step:03d}.json").write_text(
            json.dumps({"scores": [score], "total": score})
        )

    monkeypatch.setattr(runner, "_run_step", fake_step)
    monkeypatch.setattr(resampling, "invoke_agent", fake_invoke)

    trajectories = asyncio.run(runner.run_particle_filter(scenario, tmp_path))

    assert sorted(critic_calls) == [(0, 1), (1, 1), (2, 1)]
    assert len(load_trajectories(tmp_path)) == 3
    for destination, parent in enumerate([0, 0, 1]):
        trajectory = trajectories[destination]
        workspace = tmp_path / f"trajectory_{destination:03d}"
        saved_trajectory = json.loads((workspace / "trajectory.json").read_text())
        assert saved_trajectory["trajectory_id"] == destination
        assert saved_trajectory["outcome"]["final_state"] == trajectory.outcome.final_state
        assert trajectory.trajectory_id == destination
        assert [step.state_after["origin"] for step in trajectory.steps] == [parent] * 3
        assert trajectory.outcome.final_state == trajectory.steps[-1].state_after
        for step_num in range(3):
            saved_step = Step.model_validate_json(
                (workspace / "history" / f"step_{step_num:03d}_full.json").read_text()
            )
            assert saved_step.state_after == trajectory.steps[step_num].state_after


def test_particle_filter_scores_only_at_configured_interval(monkeypatch, tmp_path: Path):
    scenario = Scenario(
        name="particle-cadence",
        mode=SimMode.COUNTERFACTUAL,
        n_trajectories=3,
        step_budget=7,
        initial_state={"step": 0},
        resampling=ResamplingConfig(interval=3, min_particles=2),
    )

    async def fake_step(scenario, board, step_num, timeout, *, trajectory_id, **kwargs):
        before = board.read_state()
        after = {"step": step_num + 1}
        board.write_state(after)
        board.snapshot_state(step_num + 1)
        step = Step(step_number=step_num, state_before=before, state_after=after)
        board.save_step(step)
        return step

    scored_steps = []

    async def fake_scores(scenario, workspaces, step, timeout, agent_semaphore):
        scored_steps.append(step)
        return [1 / 3] * 3

    monkeypatch.setattr(runner, "_run_step", fake_step)
    monkeypatch.setattr(runner, "score_particles", fake_scores)

    trajectories = asyncio.run(runner.run_particle_filter(scenario, tmp_path))

    assert scored_steps == [2, 5]
    assert [len(trajectory.steps) for trajectory in trajectories] == [7, 7, 7]
