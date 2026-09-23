"""Integration coverage for particle lineage across resampling."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from minimal_agora import resampling, runner
from minimal_agora.models import ResamplingConfig, Scenario, SimMode, Step


def test_resampled_trajectory_history_matches_copied_workspace(monkeypatch, tmp_path: Path):
    scenario = Scenario(
        name="particle-lineage",
        mode=SimMode.COUNTERFACTUAL,
        n_trajectories=3,
        step_budget=3,
        initial_state={"origin": -1, "step": 0},
        resampling=ResamplingConfig(min_particles=2, ess_threshold=0.9),
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
    for destination, parent in enumerate([0, 0, 1]):
        trajectory = trajectories[destination]
        workspace = tmp_path / f"trajectory_{destination:03d}"
        assert trajectory.trajectory_id == destination
        assert [step.state_after["origin"] for step in trajectory.steps] == [parent] * 3
        assert trajectory.outcome.final_state == trajectory.steps[-1].state_after
        for step_num in range(3):
            saved_step = Step.model_validate_json(
                (workspace / "history" / f"step_{step_num:03d}_full.json").read_text()
            )
            assert saved_step.state_after == trajectory.steps[step_num].state_after
