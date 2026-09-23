from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

import structlog

from minimal_agora.agents import (
    build_resampling_critic_prompt,
    invoke_agent,
    parse_resampling_score,
)
from minimal_agora.models import (
    DEFAULT_RESAMPLING_CRITERIA,
    AgentConfig,
    AgentRole,
    ResamplingScore,
    Scenario,
)

logger = structlog.stdlib.get_logger(__name__)


def effective_sample_size(weights: list[float]) -> float:
    """ESS = 1 / sum(w_i^2) for normalized weights."""
    sum_sq = sum(w * w for w in weights)
    if sum_sq == 0.0:
        return 0.0
    return 1.0 / sum_sq


def systematic_resample(weights: list[float], n: int) -> list[int]:
    cumsum = []
    running = 0.0
    for w in weights:
        running += w
        cumsum.append(running)

    step = 1.0 / n
    u = step * 0.5
    indices = []
    i = 0
    for _ in range(n):
        while i < len(cumsum) - 1 and u > cumsum[i]:
            i += 1
        indices.append(i)
        u += step
    return indices


def compute_weights(scores: list[ResamplingScore]) -> list[float]:
    raw = [s.total + 1 for s in scores]
    total = sum(raw)
    return [r / total for r in raw]


def fork_workspace(src_workspace: Path, dst_workspace: Path) -> None:
    if dst_workspace.exists():
        shutil.rmtree(dst_workspace)
    shutil.copytree(src_workspace, dst_workspace)


def fork_resampled_workspaces(workspaces: list[Path], parent_indices: list[int]) -> None:
    """Copy from the pre-resampling generation, even when a parent is overwritten."""
    overwritten = {i for i, parent in enumerate(parent_indices) if i != parent}
    parents_to_stage = overwritten.intersection(parent_indices)
    with tempfile.TemporaryDirectory(dir=workspaces[0].parent) as tmpdir:
        staged = {}
        for i in parents_to_stage:
            staged[i] = Path(tmpdir) / f"parent_{i:03d}"
            shutil.copytree(workspaces[i], staged[i])
        for dst_idx, src_idx in enumerate(parent_indices):
            if src_idx != dst_idx:
                fork_workspace(staged.get(src_idx, workspaces[src_idx]), workspaces[dst_idx])


async def score_particles(
    scenario: Scenario,
    workspaces: list[Path],
    step: int,
    agent_timeout: int,
    agent_semaphore: asyncio.Semaphore | None,
) -> list[float]:
    """Run critics and return normalized weights without resampling."""
    resample_cfg = scenario.resampling
    if resample_cfg is None:
        n = len(workspaces)
        return [1.0 / n] * n

    criteria = resample_cfg.criteria or DEFAULT_RESAMPLING_CRITERIA
    n = len(workspaces)

    critic_agent = AgentConfig(
        role=AgentRole.RESAMPLING_CRITIC,
        name="resampling_critic",
        perspective="You evaluate trajectory quality for resampling.",
    )
    prompt = build_resampling_critic_prompt(criteria, step)

    async def run_critic(idx: int) -> None:
        ws = workspaces[idx]
        (ws / "critiques").mkdir(parents=True, exist_ok=True)
        if agent_semaphore:
            async with agent_semaphore:
                await invoke_agent(critic_agent, ws, step, prompt, agent_timeout)
        else:
            await invoke_agent(critic_agent, ws, step, prompt, agent_timeout)

    await asyncio.gather(*[run_critic(i) for i in range(n)], return_exceptions=True)

    scores: list[ResamplingScore] = []
    for i in range(n):
        score = parse_resampling_score(workspaces[i], step, trajectory_id=i)
        if score is None:
            score = ResamplingScore(trajectory_id=i, scores=[0] * len(criteria), total=0)
        scores.append(score)

    return compute_weights(scores)


async def resample_particles(
    scenario: Scenario,
    workspaces: list[Path],
    step: int,
    agent_timeout: int,
    agent_semaphore: asyncio.Semaphore | None,
) -> tuple[list[Path], list[int]]:
    resample_cfg = scenario.resampling
    if resample_cfg is None:
        return workspaces, list(range(len(workspaces)))

    criteria = resample_cfg.criteria or DEFAULT_RESAMPLING_CRITERIA
    n = len(workspaces)

    critic_agent = AgentConfig(
        role=AgentRole.RESAMPLING_CRITIC,
        name="resampling_critic",
        perspective="You evaluate trajectory quality for resampling.",
    )
    prompt = build_resampling_critic_prompt(criteria, step)

    async def run_critic(idx: int) -> None:
        ws = workspaces[idx]
        (ws / "critiques").mkdir(parents=True, exist_ok=True)
        if agent_semaphore:
            async with agent_semaphore:
                await invoke_agent(critic_agent, ws, step, prompt, agent_timeout)
        else:
            await invoke_agent(critic_agent, ws, step, prompt, agent_timeout)

    await asyncio.gather(*[run_critic(i) for i in range(n)], return_exceptions=True)

    scores: list[ResamplingScore] = []
    for i in range(n):
        score = parse_resampling_score(workspaces[i], step, trajectory_id=i)
        if score is None:
            score = ResamplingScore(trajectory_id=i, scores=[0] * len(criteria), total=0)
        scores.append(score)

    weights = compute_weights(scores)
    parent_indices = systematic_resample(weights, n)

    n_replaced = len(set(range(n)) - set(parent_indices))
    n_duplicated = len(parent_indices) - len(set(parent_indices))

    fork_resampled_workspaces(workspaces, parent_indices)

    logger.info(
        "resample.complete",
        step=step,
        n_replaced=n_replaced,
        n_duplicated=n_duplicated,
        weights=[round(w, 4) for w in weights],
        scores=[s.total for s in scores],
    )

    return workspaces, parent_indices
