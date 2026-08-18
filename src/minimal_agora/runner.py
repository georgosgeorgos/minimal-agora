from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path

import structlog

from minimal_agora.board import Board, _deep_merge
from minimal_agora.loop import (
    _classify_outcome,
    _roll_wildcard,
    _run_flat_step,
    run_trajectory,
)
from minimal_agora.models import (
    Scenario,
    Step,
    Trajectory,
    TrajectoryOutcome,
)
from minimal_agora.resampling import resample_particles
from minimal_agora.scenario import setup_workspace

logger = structlog.stdlib.get_logger(__name__)


async def run_batch(
    scenario: Scenario,
    output_dir: Path,
    concurrency: int = 4,
    agent_timeout: int = 300,
) -> list[Trajectory]:
    """Run multiple trajectories in parallel with bounded concurrency."""
    output_dir.mkdir(parents=True, exist_ok=True)
    n = scenario.n_trajectories

    semaphore = asyncio.Semaphore(concurrency)
    results: list[Trajectory] = []

    async def run_one(tid: int) -> Trajectory:
        async with semaphore:
            workspace = setup_workspace(scenario, output_dir, tid)
            print(f"[batch] starting trajectory {tid}/{n}")
            return await run_trajectory(scenario, workspace, tid, agent_timeout)

    tasks = [run_one(i) for i in range(n)]
    completed = await asyncio.gather(*tasks, return_exceptions=True)

    skipped = 0
    for i, result in enumerate(completed):
        if isinstance(result, BaseException):
            print(f"[batch] trajectory {i} failed: {result}")
        else:
            results.append(result)
            if result.outcome and result.metadata.get("resumed"):
                skipped += 1

    if skipped:
        print(f"[batch] {skipped}/{n} trajectories resumed from checkpoint")

    return results


async def run_particle_filter(
    scenario: Scenario,
    output_dir: Path,
    concurrency: int = 4,
    agent_timeout: int = 300,
) -> list[Trajectory]:
    output_dir.mkdir(parents=True, exist_ok=True)
    n = scenario.n_trajectories
    resample_cfg = scenario.resampling
    if resample_cfg is None:
        return await run_batch(scenario, output_dir, concurrency, agent_timeout)

    max_steps = scenario.termination.get("max_steps", scenario.step_budget)
    semaphore = asyncio.Semaphore(concurrency)
    agent_sem = asyncio.Semaphore(scenario.max_concurrent_agents)

    workspaces = [setup_workspace(scenario, output_dir, i) for i in range(n)]
    boards = [Board(ws) for ws in workspaces]
    all_steps: list[list[Step]] = [[] for _ in range(n)]

    for step_num in range(max_steps):
        for i in range(n):
            if scenario.wildcards_enabled:
                wildcard = _roll_wildcard(scenario.wildcards, max_steps)
                if wildcard:
                    boards[i].write_wildcard(wildcard, step_num)
                    if wildcard.state_impact:
                        state = boards[i].read_state()
                        _deep_merge(state, wildcard.state_impact)
                        boards[i].write_state(state)
                else:
                    boards[i].clear_wildcard(step_num)

        is_last = step_num == max_steps - 1

        async def run_one_step(idx: int, _boards=boards, _step_num=step_num) -> None:
            async with semaphore:
                state_before = deepcopy(_boards[idx].read_state())
                step = await _run_flat_step(
                    scenario, _boards[idx], _step_num, agent_timeout,
                    state_before, trajectory_id=idx,
                    agent_semaphore=agent_sem, max_steps=max_steps,
                )
                all_steps[idx].append(step)

        await asyncio.gather(*[run_one_step(i) for i in range(n)], return_exceptions=True)

        if (
            step_num > 0
            and step_num % resample_cfg.interval == 0
            and not is_last
            and n > resample_cfg.min_particles
        ):
            workspaces = await resample_particles(
                scenario, workspaces, step_num, agent_timeout, agent_sem,
            )
            boards = [Board(ws) for ws in workspaces]

    trajectories = []
    for i in range(n):
        final_state = boards[i].read_state()
        final_step = len(all_steps[i]) - 1
        classification = _classify_outcome(final_state, scenario)
        traj = Trajectory(
            scenario_name=scenario.name,
            trajectory_id=i,
            steps=all_steps[i],
            outcome=TrajectoryOutcome(
                classification=classification,
                final_step=final_step,
                final_state=final_state,
            ),
        )
        trajectories.append(traj)

    return trajectories
