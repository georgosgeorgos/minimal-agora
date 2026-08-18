from __future__ import annotations

import asyncio
from pathlib import Path

from minimal_agora.loop import run_trajectory
from minimal_agora.models import Scenario, Trajectory
from minimal_agora.scenario import setup_workspace


async def run_batch(
    scenario: Scenario,
    output_dir: Path,
    concurrency: int = 4,
    agent_timeout: int = 300,
) -> list[Trajectory]:
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
