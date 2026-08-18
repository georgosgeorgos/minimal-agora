from __future__ import annotations

import asyncio
import random
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import structlog

logger = structlog.stdlib.get_logger(__name__)

from minimal_agora.agents import (
    build_interaction_context,
    build_prompt,
    invoke_agent,
    parse_critique,
    parse_proposal,
    parse_resolution,
)
from minimal_agora.board import Board, _atomic_write, _deep_merge
from minimal_agora.models import (
    AgentRole,
    FitnessConfig,
    Resolution,
    Scenario,
    SimMode,
    Step,
    Trajectory,
    TrajectoryOutcome,
    TrajectoryType,
    WildcardEvent,
)


async def _invoke_with_retry(
    agent, workspace: Path, step_num: int, prompt: str, timeout: int, max_retries: int = 1,
) -> None:
    for attempt in range(1 + max_retries):
        try:
            await invoke_agent(agent, workspace, step_num, prompt, timeout)
            return
        except (OSError, RuntimeError, TimeoutError) as e:
            if attempt < max_retries:
                logger.warning("Agent %s failed (attempt %d), retrying: %s", agent.name, attempt + 1, e)
            else:
                logger.error("Agent %s failed after %d attempts: %s", agent.name, attempt + 1, e)


async def _invoke_with_semaphore(
    semaphore: asyncio.Semaphore,
    agent,
    workspace: Path,
    step_num: int,
    prompt: str,
    timeout: int,
    max_concurrent: int,
) -> None:
    if semaphore.locked():
        logger.debug("agent.throttled", agent=agent.name, waiting=True)
    async with semaphore:
        logger.debug("agent.semaphore_acquired", agent=agent.name, max_concurrent=max_concurrent)
        await _invoke_with_retry(agent, workspace, step_num, prompt, timeout)


def _detect_resume_point(workspace: Path) -> int:
    history_dir = workspace / "history"
    if not history_dir.exists():
        return 0
    completed = sorted(history_dir.glob("step_*_full.json"))
    return len(completed)


def _load_completed_trajectory(workspace: Path) -> Trajectory | None:
    path = workspace / "trajectory.json"
    if not path.exists():
        return None
    with open(path) as f:
        t = Trajectory.model_validate_json(f.read())
    return t if t.outcome is not None else None


def _restore_checkpoint(workspace: Path, resume_from: int, board: Board) -> list[Step]:
    steps = []
    for i in range(resume_from):
        step_file = workspace / "history" / f"step_{i:03d}_full.json"
        if step_file.exists():
            with open(step_file) as f:
                steps.append(Step.model_validate_json(f.read()))
    state_file = workspace / "history" / f"step_{resume_from:03d}_state.json"
    if state_file.exists():
        import json
        with open(state_file) as f:
            board.write_state(json.load(f))
    return steps


async def run_trajectory(
    scenario: Scenario,
    workspace: Path,
    trajectory_id: int = 0,
    agent_timeout: int = 300,
) -> Trajectory:
    """Run a single simulation trajectory, returning the completed Trajectory with outcome."""
    board = Board(workspace)
    agent_semaphore = asyncio.Semaphore(scenario.max_concurrent_agents)

    tlog = logger.bind(trajectory_id=trajectory_id)

    existing = _load_completed_trajectory(workspace)
    if existing is not None:
        tlog.info("trajectory.skip", reason="already_complete")
        return existing

    resume_from = _detect_resume_point(workspace)
    trajectory = Trajectory(
        scenario_name=scenario.name,
        trajectory_id=trajectory_id,
    )

    if resume_from > 0:
        tlog.info("trajectory.resume", from_step=resume_from)
        trajectory.steps = _restore_checkpoint(workspace, resume_from, board)
        trajectory.metadata["resumed"] = True
        trajectory.metadata["resume_from_step"] = resume_from
        trajectory.metadata["resume_timestamp"] = datetime.now(UTC).isoformat()

    max_steps = scenario.termination.get("max_steps", scenario.step_budget)
    conditions = scenario.termination.get("conditions", [])
    fitness_history: list[float | None] = []
    plateau_window = scenario.termination.get("plateau_window", 5)
    plateau_threshold = scenario.termination.get("plateau_threshold", 0.01)

    for step_num in range(resume_from, max_steps):
        slog = tlog.bind(step=step_num, max_steps=max_steps)
        wildcard = _roll_wildcard(scenario.wildcards, max_steps) if scenario.wildcards_enabled else None
        if wildcard:
            slog.info("step.start", wildcard=wildcard.name)
            board.write_wildcard(wildcard, step_num)
            if wildcard.state_impact:
                state = board.read_state()
                _deep_merge(state, wildcard.state_impact)
                board.write_state(state)
        else:
            slog.info("step.start")
            board.clear_wildcard(step_num)

        step = await _run_step(scenario, board, step_num, agent_timeout, trajectory_id, agent_semaphore)
        trajectory.steps.append(step)

        if scenario.fitness:
            score = _evaluate_fitness(step.state_after, scenario.fitness)
            fitness_history.append(score)
            if score is not None:
                slog.info("step.fitness", score=score)

        if _check_termination(step.state_after, conditions):
            slog.info("trajectory.terminated", reason="condition_met")
            break

        if scenario.mode == SimMode.OPEN_ENDED and scenario.fitness and _check_plateau(
            fitness_history, plateau_window, plateau_threshold,
        ):
            slog.info("trajectory.terminated", reason="fitness_plateau")
            break

    final_state = board.read_state()
    final_step = len(trajectory.steps) - 1

    if fitness_history:
        trajectory.metadata["fitness_history"] = fitness_history

    classification = _classify_outcome(final_state, scenario)
    trajectory.outcome = TrajectoryOutcome(
        classification=classification,
        final_step=final_step,
        final_state=final_state,
    )

    _save_trajectory(trajectory, workspace)
    return trajectory


async def _run_step(
    scenario: Scenario,
    board: Board,
    step_num: int,
    timeout: int,
    trajectory_id: int = 0,
    agent_semaphore: asyncio.Semaphore | None = None,
) -> Step:
    state_before = deepcopy(board.read_state())

    if scenario.entities:
        return await _run_entity_step(scenario, board, step_num, timeout, state_before, trajectory_id, agent_semaphore)
    return await _run_flat_step(scenario, board, step_num, timeout, state_before, trajectory_id, agent_semaphore)


async def _run_flat_step(
    scenario: Scenario,
    board: Board,
    step_num: int,
    timeout: int,
    state_before: dict,
    trajectory_id: int = 0,
    agent_semaphore: asyncio.Semaphore | None = None,
) -> Step:
    actors = [a for a in scenario.agents if a.role == AgentRole.ACTOR]
    critics = [a for a in scenario.agents if a.role == AgentRole.CRITIC]
    judges = [a for a in scenario.agents if a.role == AgentRole.JUDGE]

    max_concurrent = scenario.max_concurrent_agents
    rules = scenario.rules
    actor_tasks = [
        _invoke_with_semaphore(
            agent_semaphore, a, board.workspace, step_num,
            build_prompt(a, step_num, rules, trajectory_id=trajectory_id),
            timeout, max_concurrent,
        ) if agent_semaphore else _invoke_with_retry(
            a, board.workspace, step_num,
            build_prompt(a, step_num, rules, trajectory_id=trajectory_id),
            timeout,
        )
        for a in actors
    ]
    await asyncio.gather(*actor_tasks, return_exceptions=True)

    proposals = []
    for a in actors:
        p = parse_proposal(board.workspace, a.name, step_num)
        if p:
            proposals.append(p)
            board.save_proposal(p, step_num)

    critiques = []
    if critics:
        critic_tasks = [
            _invoke_with_semaphore(
                agent_semaphore, c, board.workspace, step_num,
                build_prompt(c, step_num, rules), timeout, max_concurrent,
            ) if agent_semaphore else _invoke_with_retry(
                c, board.workspace, step_num, build_prompt(c, step_num, rules), timeout,
            )
            for c in critics
        ]
        await asyncio.gather(*critic_tasks, return_exceptions=True)

        for c in critics:
            cr = parse_critique(board.workspace, c.name, step_num)
            if cr:
                critiques.append(cr)
                board.save_critique(cr, step_num)

    resolution = None
    if judges:
        judge = judges[0]
        await _invoke_with_retry(judge, board.workspace, step_num, build_prompt(judge, step_num, rules), timeout)
        resolution = parse_resolution(board.workspace, step_num)

    if resolution is None:
        resolution = _fallback_resolution(proposals)

    board.save_resolution(resolution, step_num)
    state_after = board.apply_resolution(resolution, step_num)

    step = Step(
        step_number=step_num,
        proposals=proposals,
        critiques=critiques,
        resolution=resolution,
        state_before=state_before,
        state_after=state_after,
    )
    board.save_step(step)
    return step


async def _run_entity_step(
    scenario: Scenario,
    board: Board,
    step_num: int,
    timeout: int,
    state_before: dict,
    trajectory_id: int = 0,
    agent_semaphore: asyncio.Semaphore | None = None,
) -> Step:
    rules = scenario.rules
    max_concurrent = scenario.max_concurrent_agents
    proposals = []
    critiques = []

    force_entities = [e for e in scenario.entities if e.type == TrajectoryType.FORCE]
    pop_entities = [e for e in scenario.entities if e.type == TrajectoryType.POPULATION]
    critic_entities = [e for e in scenario.entities if e.type == TrajectoryType.CRITIC]
    eval_entities = [e for e in scenario.entities if e.type == TrajectoryType.EVALUATOR]

    # Phase 1: Forces propose world-level changes
    force_agents = [a for e in force_entities for a in e.agents]
    if force_agents:
        force_tasks = [
            _invoke_with_semaphore(
                agent_semaphore, a, board.workspace, step_num,
                build_prompt(a, step_num, rules, trajectory_id=trajectory_id),
                timeout, max_concurrent,
            ) if agent_semaphore else _invoke_with_retry(
                a, board.workspace, step_num,
                build_prompt(a, step_num, rules, trajectory_id=trajectory_id),
                timeout,
            )
            for a in force_agents
        ]
        await asyncio.gather(*force_tasks, return_exceptions=True)
        for a in force_agents:
            p = parse_proposal(board.workspace, a.name, step_num)
            if p:
                proposals.append(p)
                board.save_proposal(p, step_num)

    # Phase 2: Populations propose their changes (in parallel)
    # Build interaction context per entity so agents see neighbor state
    current_state = board.read_state()
    entity_interaction: dict[str, str] = {}
    for entity in pop_entities:
        ctx = build_interaction_context(entity, scenario.entities, current_state, step_num)
        for a in entity.agents:
            entity_interaction[a.name] = ctx

    pop_agents = [a for e in pop_entities for a in e.agents]
    if pop_agents:
        pop_tasks = [
            _invoke_with_semaphore(
                agent_semaphore, a, board.workspace, step_num,
                build_prompt(a, step_num, rules, entity_interaction.get(a.name, ""), trajectory_id=trajectory_id),
                timeout, max_concurrent,
            ) if agent_semaphore else _invoke_with_retry(
                a, board.workspace, step_num,
                build_prompt(a, step_num, rules, entity_interaction.get(a.name, ""), trajectory_id=trajectory_id),
                timeout,
            )
            for a in pop_agents
        ]
        await asyncio.gather(*pop_tasks, return_exceptions=True)
        for a in pop_agents:
            p = parse_proposal(board.workspace, a.name, step_num)
            if p:
                proposals.append(p)
                board.save_proposal(p, step_num)

    # Phase 3: Critics evaluate all proposals
    critic_agents = [a for e in critic_entities for a in e.agents]
    if critic_agents:
        critic_tasks = [
            _invoke_with_semaphore(
                agent_semaphore, c, board.workspace, step_num,
                build_prompt(c, step_num, rules), timeout, max_concurrent,
            ) if agent_semaphore else _invoke_with_retry(
                c, board.workspace, step_num, build_prompt(c, step_num, rules), timeout,
            )
            for c in critic_agents
        ]
        await asyncio.gather(*critic_tasks, return_exceptions=True)
        for c in critic_agents:
            cr = parse_critique(board.workspace, c.name, step_num)
            if cr:
                critiques.append(cr)
                board.save_critique(cr, step_num)

    # Phase 4: Evaluator resolves everything
    resolution = None
    eval_agents = [a for e in eval_entities for a in e.agents if a.role == AgentRole.JUDGE]
    if eval_agents:
        judge = eval_agents[0]
        await _invoke_with_retry(judge, board.workspace, step_num, build_prompt(judge, step_num, rules), timeout)
        resolution = parse_resolution(board.workspace, step_num)

    if resolution is None:
        resolution = _fallback_resolution(proposals)

    board.save_resolution(resolution, step_num)
    state_after = board.apply_resolution(resolution, step_num)

    step = Step(
        step_number=step_num,
        proposals=proposals,
        critiques=critiques,
        resolution=resolution,
        state_before=state_before,
        state_after=state_after,
    )
    board.save_step(step)
    return step


def _fallback_resolution(proposals: list) -> Resolution:
    merged: dict = {}
    reasoning_parts = []
    for p in proposals:
        _deep_merge(merged, p.proposed_changes)
        reasoning_parts.append(f"{p.agent}: {p.reasoning}")

    return Resolution(
        state_delta=merged,
        narrative="Changes applied from all proposals without judge resolution.",
        reasoning="\n".join(reasoning_parts),
    )


def _check_termination(state: dict, conditions: list[dict]) -> bool:
    for cond in conditions:
        field = cond.get("field", "")
        value = _get_nested(state, field)
        if value is None:
            continue
        if "equals" in cond and value == cond["equals"]:
            return True
        if "greater_than" in cond and isinstance(value, (int, float)) and value > cond["greater_than"]:
            return True
        if "less_than" in cond and isinstance(value, (int, float)) and value < cond["less_than"]:
            return True
    return False


def _classify_outcome(state: dict, scenario: Scenario) -> str:
    if scenario.outcome is None:
        return "unclassified"

    for oc in scenario.outcome.classifier:
        if oc.default:
            continue
        if oc.condition is None:
            continue
        value = _get_nested(state, oc.condition.field)
        if value is None:
            continue
        if oc.condition.equals is not None and value == oc.condition.equals:
            return oc.name
        if oc.condition.greater_than is not None and isinstance(value, (int, float)) and value > oc.condition.greater_than:
            return oc.name
        if oc.condition.less_than is not None and isinstance(value, (int, float)) and value < oc.condition.less_than:
            return oc.name

    for oc in scenario.outcome.classifier:
        if oc.default:
            return oc.name

    return "unclassified"


def _roll_wildcard(wildcards: list[WildcardEvent], max_steps: int = 1) -> WildcardEvent | None:
    for event in wildcards:
        per_step = min(event.probability / max_steps, 1.0)
        if random.random() < per_step:
            return event
    return None


def _get_nested(d: dict, path: str):
    keys = path.split(".")
    current = d
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _evaluate_fitness(state: dict, fitness: FitnessConfig) -> float | None:
    value = _get_nested(state, fitness.metric)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _check_plateau(
    history: list[float | None], window: int, threshold: float,
) -> bool:
    valid = [v for v in history if v is not None]
    if len(valid) < window:
        return False
    recent = valid[-window:]
    return max(recent) - min(recent) < threshold


def _save_trajectory(trajectory: Trajectory, workspace: Path) -> None:
    path = workspace / "trajectory.json"
    with _atomic_write(path) as f:
        f.write(trajectory.model_dump_json(indent=2))
