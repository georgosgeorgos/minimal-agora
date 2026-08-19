from __future__ import annotations

import asyncio
import random
import time
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
    parse_critique_from_text,
    parse_proposal,
    parse_proposal_from_text,
    parse_resolution,
    parse_resolution_from_text,
)
from minimal_agora.board import (
    Board,
    _atomic_write,
    _deep_merge,
    _expand_dotted_keys,
    compress_narrative,
    evaluate_wildcard_mode,
)
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


async def _safe_invoke(coro) -> None:
    try:
        await coro
    except Exception as e:  # noqa: BLE001
        logger.warning("agent.task_failed", error=str(e))


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
        if scenario.wildcards_enabled:
            current_state = board.read_state()
            wildcard = _roll_wildcard(
                scenario.wildcards, max_steps, current_state,
                step_num=step_num, warmup=scenario.wildcard_warmup,
            )
        else:
            wildcard = None
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

        step = await _run_step(scenario, board, step_num, agent_timeout, trajectory_id, agent_semaphore, max_steps)
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
    max_steps: int = 1,
) -> Step:
    if scenario.narrative_window is not None:
        raw = board.narrative_path.read_text()
        compressed = compress_narrative(raw, scenario.narrative_window)
        if compressed != raw:
            logger.info("Compressed narrative: %d → %d chars", len(raw), len(compressed))
            board.narrative_path.write_text(compressed)

    state_before = deepcopy(board.read_state())

    if scenario.entities:
        return await _run_entity_step(scenario, board, step_num, timeout, state_before, trajectory_id, agent_semaphore)
    return await _run_flat_step(scenario, board, step_num, timeout, state_before, trajectory_id, agent_semaphore, max_steps)


def _read_narrative(board: Board) -> str:
    try:
        return board.narrative_path.read_text()
    except FileNotFoundError:
        return ""


def _read_wildcard_dict(board: Board, step_num: int) -> dict | None:
    import json as _json
    path = board.workspace / "board" / f"wildcard_step_{step_num:03d}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return _json.load(f)


async def _invoke_and_collect(
    agent,
    workspace: Path,
    step_num: int,
    prompt: str,
    timeout: int,
    agent_semaphore: asyncio.Semaphore | None,
    max_concurrent: int,
) -> str | None:
    try:
        if agent_semaphore:
            if agent_semaphore.locked():
                logger.debug("agent.throttled", agent=agent.name, waiting=True)
            async with agent_semaphore:
                logger.debug("agent.semaphore_acquired", agent=agent.name, max_concurrent=max_concurrent)
                return await _invoke_with_retry_return(agent, workspace, step_num, prompt, timeout)
        else:
            return await _invoke_with_retry_return(agent, workspace, step_num, prompt, timeout)
    except Exception as e:  # noqa: BLE001
        logger.warning("agent.task_failed", agent=agent.name, error=str(e))
        return None


async def _invoke_with_retry_return(
    agent, workspace: Path, step_num: int, prompt: str, timeout: int, max_retries: int = 1,
) -> str | None:
    for attempt in range(1 + max_retries):
        try:
            return await invoke_agent(agent, workspace, step_num, prompt, timeout)
        except (OSError, RuntimeError, TimeoutError) as e:
            if attempt < max_retries:
                logger.warning("Agent %s failed (attempt %d), retrying: %s", agent.name, attempt + 1, e)
            else:
                logger.error("Agent %s failed after %d attempts: %s", agent.name, attempt + 1, e)
    return None


async def _run_flat_step(
    scenario: Scenario,
    board: Board,
    step_num: int,
    timeout: int,
    state_before: dict,
    trajectory_id: int = 0,
    agent_semaphore: asyncio.Semaphore | None = None,
    max_steps: int = 1,
) -> Step:
    actors = [a for a in scenario.agents if a.role == AgentRole.ACTOR]
    critics = [a for a in scenario.agents if a.role == AgentRole.CRITIC]
    judges = [a for a in scenario.agents if a.role == AgentRole.JUDGE]

    max_concurrent = scenario.max_concurrent_agents
    rules = scenario.rules

    current_state = board.read_state()
    narrative_text = _read_narrative(board)
    wildcard_dict = _read_wildcard_dict(board, step_num)

    embed_kwargs: dict = {
        "state": current_state,
        "narrative": narrative_text,
        "wildcard": wildcard_dict,
    }

    logger.debug("flat_step.propose_start", step=step_num, n_actors=len(actors))
    t0 = time.monotonic()

    actor_outputs: dict[str, str | None] = {}

    async def _run_actor(a):
        prompt = build_prompt(a, step_num, rules, trajectory_id=trajectory_id, **embed_kwargs)
        result = await _invoke_and_collect(
            a, board.workspace, step_num, prompt, timeout, agent_semaphore, max_concurrent,
        )
        actor_outputs[a.name] = result

    try:
        async with asyncio.TaskGroup() as tg:
            for a in actors:
                tg.create_task(_run_actor(a))
    except ExceptionGroup as eg:
        for exc in eg.exceptions:
            logger.error("flat_step.propose.unhandled_failure", step=step_num, error=str(exc))
    logger.debug("flat_step.propose_done", step=step_num, duration_s=round(time.monotonic() - t0, 3))

    proposals = []
    for a in actors:
        output = actor_outputs.get(a.name)
        p = None
        if output:
            p = parse_proposal_from_text(output, a.name)
        if p is None:
            p = parse_proposal(board.workspace, a.name, step_num)
        if p:
            proposals.append(p)
            board.save_proposal(p, step_num)

    is_review_step = (
        scenario.review_interval == 1
        or (step_num % scenario.review_interval == 0)
        or (step_num == max_steps - 1)
    )

    critiques = []
    resolution = None

    if is_review_step:
        if critics:
            proposals_dicts = [p.model_dump() for p in proposals]
            critic_kwargs = {**embed_kwargs, "proposals": proposals_dicts}

            logger.debug("flat_step.critique_start", step=step_num, n_critics=len(critics))
            t1 = time.monotonic()

            critic_outputs: dict[str, str | None] = {}

            async def _run_critic(c):
                prompt = build_prompt(c, step_num, rules, **critic_kwargs)
                result = await _invoke_and_collect(
                    c, board.workspace, step_num, prompt, timeout, agent_semaphore, max_concurrent,
                )
                critic_outputs[c.name] = result

            try:
                async with asyncio.TaskGroup() as tg:
                    for c in critics:
                        tg.create_task(_run_critic(c))
            except ExceptionGroup as eg:
                for exc in eg.exceptions:
                    logger.error(
                        "flat_step.critique.unhandled_failure", step=step_num, error=str(exc),
                    )
            logger.debug(
                "flat_step.critique_done", step=step_num,
                duration_s=round(time.monotonic() - t1, 3),
            )

            for c in critics:
                output = critic_outputs.get(c.name)
                cr = None
                if output:
                    cr = parse_critique_from_text(output, c.name)
                if cr is None:
                    cr = parse_critique(board.workspace, c.name, step_num)
                if cr:
                    critiques.append(cr)
                    board.save_critique(cr, step_num)

        if judges:
            logger.debug("flat_step.resolve_start", step=step_num)
            t2 = time.monotonic()
            judge = judges[0]
            judge_kwargs = {
                **embed_kwargs,
                "proposals": [p.model_dump() for p in proposals],
                "critiques": [c.model_dump() for c in critiques],
            }
            prompt = build_prompt(judge, step_num, rules, **judge_kwargs)
            judge_output = await _invoke_with_retry_return(
                judge, board.workspace, step_num, prompt, timeout,
            )
            if judge_output:
                resolution = parse_resolution_from_text(judge_output)
            if resolution is None:
                resolution = parse_resolution(board.workspace, step_num)
            logger.debug(
                "flat_step.resolve_done", step=step_num,
                duration_s=round(time.monotonic() - t2, 3),
            )

        if resolution is None:
            resolution = _fallback_resolution(proposals)

        board.save_resolution(resolution, step_num)
        state_after = board.apply_resolution(resolution, step_num)
    else:
        next_review_step = ((step_num // scenario.review_interval) + 1) * scenario.review_interval
        logger.debug(
            "step.auto_merge",
            step=step_num,
            n_proposals=len(proposals),
            next_review_step=next_review_step,
        )

        merged_state = deepcopy(state_before)
        for p in proposals:
            expanded = _expand_dotted_keys(p.proposed_changes)
            _deep_merge(merged_state, expanded)
        board.write_state(merged_state)
        board.snapshot_state(step_num + 1)

        narrative = (
            f"Step {step_num}: Auto-merged {len(proposals)} actor proposals "
            f"(review scheduled at step {next_review_step})."
        )
        board._append_narrative(narrative, step_num)

        state_after = merged_state

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

    logger.debug(
        "entity_step.order",
        step=step_num,
        n_forces=len(force_entities),
        n_populations=len(pop_entities),
        n_critics=len(critic_entities),
        n_evaluators=len(eval_entities),
    )

    current_state = board.read_state()
    narrative_text = _read_narrative(board)
    wildcard_dict = _read_wildcard_dict(board, step_num)
    embed_kwargs: dict = {
        "state": current_state,
        "narrative": narrative_text,
        "wildcard": wildcard_dict,
    }

    # Phase 1: Forces propose world-level changes
    force_agents = [a for e in force_entities for a in e.agents]
    if force_agents:
        logger.debug("entity_step.forces_start", step=step_num, n_agents=len(force_agents))
        t0 = time.monotonic()
        force_outputs: dict[str, str | None] = {}

        async def _run_force(a):
            prompt = build_prompt(a, step_num, rules, trajectory_id=trajectory_id, **embed_kwargs)
            result = await _invoke_and_collect(
                a, board.workspace, step_num, prompt, timeout, agent_semaphore, max_concurrent,
            )
            force_outputs[a.name] = result

        try:
            async with asyncio.TaskGroup() as tg:
                for a in force_agents:
                    tg.create_task(_run_force(a))
        except ExceptionGroup as eg:
            for exc in eg.exceptions:
                logger.error(
                    "entity_step.forces.unhandled_failure", step=step_num, error=str(exc),
                )
        logger.debug(
            "entity_step.forces_done", step=step_num,
            duration_s=round(time.monotonic() - t0, 3),
        )
        for a in force_agents:
            output = force_outputs.get(a.name)
            p = None
            if output:
                p = parse_proposal_from_text(output, a.name)
            if p is None:
                p = parse_proposal(board.workspace, a.name, step_num)
            if p:
                proposals.append(p)
                board.save_proposal(p, step_num)

    # Phase 2: Populations propose their changes (in parallel)
    current_state = board.read_state()
    entity_interaction: dict[str, str] = {}
    for entity in pop_entities:
        ctx = build_interaction_context(entity, scenario.entities, current_state, step_num)
        for a in entity.agents:
            entity_interaction[a.name] = ctx

    embed_kwargs["state"] = current_state

    pop_agents = [a for e in pop_entities for a in e.agents]
    if pop_agents:
        logger.debug("entity_step.populations_start", step=step_num, n_agents=len(pop_agents))
        t1 = time.monotonic()
        pop_outputs: dict[str, str | None] = {}

        async def _run_pop(a):
            prompt = build_prompt(
                a, step_num, rules, entity_interaction.get(a.name, ""),
                trajectory_id=trajectory_id, **embed_kwargs,
            )
            result = await _invoke_and_collect(
                a, board.workspace, step_num, prompt, timeout, agent_semaphore, max_concurrent,
            )
            pop_outputs[a.name] = result

        try:
            async with asyncio.TaskGroup() as tg:
                for a in pop_agents:
                    tg.create_task(_run_pop(a))
        except ExceptionGroup as eg:
            for exc in eg.exceptions:
                logger.error(
                    "entity_step.populations.unhandled_failure", step=step_num, error=str(exc),
                )
        logger.debug(
            "entity_step.populations_done", step=step_num,
            duration_s=round(time.monotonic() - t1, 3),
        )
        for a in pop_agents:
            output = pop_outputs.get(a.name)
            p = None
            if output:
                p = parse_proposal_from_text(output, a.name)
            if p is None:
                p = parse_proposal(board.workspace, a.name, step_num)
            if p:
                proposals.append(p)
                board.save_proposal(p, step_num)

    # Phase 3: Critics evaluate all proposals
    critic_agents = [a for e in critic_entities for a in e.agents]
    if critic_agents:
        proposals_dicts = [p.model_dump() for p in proposals]
        critic_kwargs = {**embed_kwargs, "proposals": proposals_dicts}

        logger.debug("entity_step.critics_start", step=step_num, n_agents=len(critic_agents))
        t2 = time.monotonic()
        critic_outputs: dict[str, str | None] = {}

        async def _run_critic(c):
            prompt = build_prompt(c, step_num, rules, **critic_kwargs)
            result = await _invoke_and_collect(
                c, board.workspace, step_num, prompt, timeout, agent_semaphore, max_concurrent,
            )
            critic_outputs[c.name] = result

        try:
            async with asyncio.TaskGroup() as tg:
                for c in critic_agents:
                    tg.create_task(_run_critic(c))
        except ExceptionGroup as eg:
            for exc in eg.exceptions:
                logger.error(
                    "entity_step.critics.unhandled_failure", step=step_num, error=str(exc),
                )
        logger.debug(
            "entity_step.critics_done", step=step_num,
            duration_s=round(time.monotonic() - t2, 3),
        )
        for c in critic_agents:
            output = critic_outputs.get(c.name)
            cr = None
            if output:
                cr = parse_critique_from_text(output, c.name)
            if cr is None:
                cr = parse_critique(board.workspace, c.name, step_num)
            if cr:
                critiques.append(cr)
                board.save_critique(cr, step_num)

    # Phase 4: Evaluator resolves everything
    resolution = None
    eval_agents = [a for e in eval_entities for a in e.agents if a.role == AgentRole.JUDGE]
    if eval_agents:
        logger.debug("entity_step.resolve_start", step=step_num)
        t3 = time.monotonic()
        judge = eval_agents[0]
        judge_kwargs = {
            **embed_kwargs,
            "proposals": [p.model_dump() for p in proposals],
            "critiques": [c.model_dump() for c in critiques],
        }
        prompt = build_prompt(judge, step_num, rules, **judge_kwargs)
        judge_output = await _invoke_with_retry_return(
            judge, board.workspace, step_num, prompt, timeout,
        )
        if judge_output:
            resolution = parse_resolution_from_text(judge_output)
        if resolution is None:
            resolution = parse_resolution(board.workspace, step_num)
        logger.debug(
            "entity_step.resolve_done", step=step_num,
            duration_s=round(time.monotonic() - t3, 3),
        )

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
            logger.debug("termination.condition_skip", field=field, reason="field_not_found")
            continue
        if "equals" in cond and value == cond["equals"]:
            logger.debug("termination.condition_met", field=field, op="equals", value=value)
            return True
        if "greater_than" in cond and isinstance(value, (int, float)) and value > cond["greater_than"]:
            logger.debug(
                "termination.condition_met", field=field, op="greater_than",
                value=value, threshold=cond["greater_than"],
            )
            return True
        if "less_than" in cond and isinstance(value, (int, float)) and value < cond["less_than"]:
            logger.debug(
                "termination.condition_met", field=field, op="less_than",
                value=value, threshold=cond["less_than"],
            )
            return True
        logger.debug("termination.condition_not_met", field=field, value=value)
    return False


def _classify_outcome(state: dict, scenario: Scenario) -> str:
    if scenario.outcome is None:
        logger.debug("classify.skip", reason="no_outcome_config")
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
            logger.info("classify.result", classification=oc.name)
            return oc.name
        if oc.condition.greater_than is not None and isinstance(value, (int, float)) and value > oc.condition.greater_than:
            logger.info("classify.result", classification=oc.name)
            return oc.name
        if oc.condition.less_than is not None and isinstance(value, (int, float)) and value < oc.condition.less_than:
            logger.info("classify.result", classification=oc.name)
            return oc.name

    for oc in scenario.outcome.classifier:
        if oc.default:
            logger.info("classify.result", classification=oc.name, default=True)
            return oc.name

    logger.info("classify.result", classification="unclassified", default=True)
    return "unclassified"


def _roll_wildcard(
    wildcards: list[WildcardEvent],
    max_steps: int = 1,
    state: dict | None = None,
    step_num: int = 0,
    warmup: float = 0.05,
) -> WildcardEvent | None:
    if step_num < int(max_steps * warmup):
        logger.debug("wildcard.warmup_suppressed", step=step_num)
        return None
    for event in wildcards:
        per_step = min(event.probability / max_steps, 1.0)
        effective_prob = evaluate_wildcard_mode(event, per_step, state)
        if effective_prob is None:
            continue
        if random.random() < effective_prob:
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
