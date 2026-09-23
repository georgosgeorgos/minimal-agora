from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import structlog

from minimal_agora.board import Board, _deep_merge
from minimal_agora.loop import (
    _classify_outcome,
    _roll_wildcard,
    _run_step,
    run_trajectory,
)
from minimal_agora.models import (
    Scenario,
    Step,
    StepExecutionMode,
    Trajectory,
    TrajectoryOutcome,
)
from minimal_agora.resampling import (
    effective_sample_size,
    resample_particles,
    score_particles,
)
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
    completed: list[Trajectory | BaseException | None] = [None] * n

    logger.info("batch.start", n_trajectories=n, concurrency=concurrency)
    t0 = time.monotonic()

    async def _safe_run_one(tid: int) -> None:
        try:
            async with semaphore:
                workspace = setup_workspace(scenario, output_dir, tid)
                print(f"[batch] starting trajectory {tid}/{n}")
                completed[tid] = await run_trajectory(scenario, workspace, tid, agent_timeout)
        except Exception as e:  # noqa: BLE001
            logger.warning("trajectory.failed", trajectory_id=tid, error=str(e))
            completed[tid] = e

    try:
        async with asyncio.TaskGroup() as tg:
            for i in range(n):
                tg.create_task(_safe_run_one(i))
    except ExceptionGroup as eg:
        for exc in eg.exceptions:
            logger.error("batch.unhandled_failure", error=str(exc))

    n_failed = 0
    skipped = 0
    for i, result in enumerate(completed):
        if isinstance(result, BaseException):
            print(f"[batch] trajectory {i} failed: {result}")
            n_failed += 1
        elif result is not None:
            results.append(result)
            if result.outcome and result.metadata.get("resumed"):
                skipped += 1

    if skipped:
        print(f"[batch] {skipped}/{n} trajectories resumed from checkpoint")

    logger.info(
        "batch.complete",
        n_completed=len(results),
        n_failed=n_failed,
        duration_s=round(time.monotonic() - t0, 3),
    )

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

    logger.info("filter.start", n_trajectories=n, concurrency=concurrency)
    t0 = time.monotonic()

    max_steps = scenario.termination.get("max_steps", scenario.step_budget)
    semaphore = asyncio.Semaphore(concurrency)
    agent_sem = asyncio.Semaphore(scenario.max_concurrent_agents)

    workspaces = [setup_workspace(scenario, output_dir, i) for i in range(n)]
    boards = [Board(ws) for ws in workspaces]
    all_steps: list[list[Step]] = [[] for _ in range(n)]
    ess_history: list[float] = []
    ess_thresh = resample_cfg.ess_threshold

    for step_num in range(max_steps):
        for i in range(n):
            if scenario.wildcards_enabled:
                current_state = boards[i].read_state()
                wildcard = _roll_wildcard(
                    scenario.wildcards, max_steps, current_state, step_num, scenario.wildcard_warmup
                )
                if wildcard:
                    boards[i].write_wildcard(wildcard, step_num)
                    if wildcard.state_impact:
                        state = boards[i].read_state()
                        _deep_merge(state, wildcard.state_impact)
                        boards[i].write_state(state)
                else:
                    boards[i].clear_wildcard(step_num)

        is_last = step_num == max_steps - 1

        async def _safe_run_step(idx: int, _boards=boards, _step_num=step_num) -> None:
            try:
                async with semaphore:
                    step = await _run_step(
                        scenario,
                        _boards[idx],
                        _step_num,
                        agent_timeout,
                        trajectory_id=idx,
                        agent_semaphore=agent_sem,
                        max_steps=max_steps,
                    )
                    all_steps[idx].append(step)
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "particle.step_failed",
                    trajectory_id=idx,
                    step=_step_num,
                    error=str(e),
                )

        try:
            async with asyncio.TaskGroup() as tg:
                for i in range(n):
                    tg.create_task(_safe_run_step(i))
        except ExceptionGroup as eg:
            for exc in eg.exceptions:
                logger.error("filter.step.unhandled_failure", step=step_num, error=str(exc))

        if (
            step_num > 0
            and not is_last
            and n > resample_cfg.min_particles
            and (step_num + 1) % resample_cfg.interval == 0
        ):
            weights = await score_particles(
                scenario,
                workspaces,
                step_num,
                agent_timeout,
                agent_sem,
            )
            ess = effective_sample_size(weights)
            ess_history.append(ess)
            threshold_value = ess_thresh * n
            triggered = ess < threshold_value

            logger.debug(
                "filter.ess",
                step=step_num,
                ess=round(ess, 4),
                threshold=round(threshold_value, 4),
                resampling_triggered=triggered,
            )

            if triggered:
                logger.info("filter.resample", step=step_num, ess=round(ess, 4))
                workspaces, parent_indices = resample_particles(workspaces, weights, step_num)
                all_steps[:] = [list(all_steps[parent_idx]) for parent_idx in parent_indices]
                boards = [Board(ws) for ws in workspaces]
        else:
            ess_history.append(float(n))

    trajectories = []
    for i in range(n):
        final_state = boards[i].read_state()
        final_step = len(all_steps[i]) - 1
        classification = _classify_outcome(final_state, scenario)
        metadata: dict[str, Any] = {"ess_history": ess_history}
        if scenario.adaptive_steps is not None:
            routine_steps = sum(
                step.execution_mode == StepExecutionMode.ROUTINE for step in all_steps[i]
            )
            metadata["adaptive_steps"] = {
                "reasoned_steps": len(all_steps[i]) - routine_steps,
                "routine_steps": routine_steps,
                "llm_steps_skipped": routine_steps,
            }
        traj = Trajectory(
            scenario_name=scenario.name,
            trajectory_id=i,
            steps=all_steps[i],
            outcome=TrajectoryOutcome(
                classification=classification,
                final_step=final_step,
                final_state=final_state,
            ),
            metadata=metadata,
        )
        trajectories.append(traj)

    logger.info(
        "filter.complete",
        n_trajectories=len(trajectories),
        duration_s=round(time.monotonic() - t0, 3),
    )

    return trajectories
