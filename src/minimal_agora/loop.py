from __future__ import annotations

import asyncio
import random
import time
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

logger = structlog.stdlib.get_logger(__name__)

from minimal_agora.agents import (
    build_interaction_context,
    build_prompt,
    detect_conflicts,
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
    AgentCallTokens,
    AgentRole,
    FitnessConfig,
    Resolution,
    Scenario,
    SimMode,
    Step,
    StepTokenUsage,
    Trajectory,
    TrajectoryOutcome,
    TrajectoryType,
    WildcardEvent,
)
from minimal_agora.providers.protocol import AgentInvocationResult
from minimal_agora.schema import infer_schema, validate_state_delta


async def _safe_invoke(coro) -> None:
    try:
        await coro
    except Exception as e:  # noqa: BLE001
        logger.warning("agent.task_failed", error=str(e))


async def _invoke_with_retry(
    agent, workspace: Path, step_num: int, prompt: str, timeout: int, max_retries: int = 1,
) -> AgentInvocationResult | None:
    for attempt in range(1 + max_retries):
        try:
            return await invoke_agent(agent, workspace, step_num, prompt, timeout)
        except (OSError, RuntimeError, TimeoutError) as e:
            if attempt < max_retries:
                logger.warning("Agent %s failed (attempt %d), retrying: %s", agent.name, attempt + 1, e)
            else:
                logger.error("Agent %s failed after %d attempts: %s", agent.name, attempt + 1, e)
    return None


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

    state_schema = infer_schema(scenario.initial_state)
    if state_schema:
        tlog.info("trajectory.schema_inferred", n_fields=len(state_schema))

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

        step = await _run_step(scenario, board, step_num, agent_timeout, trajectory_id, agent_semaphore, max_steps, state_schema)
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

    trajectory.total_tokens = _aggregate_trajectory_tokens(trajectory.steps)

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
    state_schema: dict | None = None,
) -> Step:
    if scenario.narrative_window is not None:
        raw = board.narrative_path.read_text()
        compressed = compress_narrative(raw, scenario.narrative_window)
        if compressed != raw:
            logger.info("Compressed narrative: %d → %d chars", len(raw), len(compressed))
            board.narrative_path.write_text(compressed)

    state_before = deepcopy(board.read_state())

    if scenario.entities:
        return await _run_entity_step(scenario, board, step_num, timeout, state_before, trajectory_id, agent_semaphore, state_schema, max_steps)
    return await _run_flat_step(scenario, board, step_num, timeout, state_before, trajectory_id, agent_semaphore, max_steps, state_schema)


def _collect_tokens_from_result(
    result: AgentInvocationResult | None,
    role: str,
    token_calls: list[AgentCallTokens],
) -> None:
    if result is None:
        return
    input_t = result.input_tokens or 0
    output_t = result.output_tokens or 0
    if input_t or output_t:
        token_calls.append(AgentCallTokens(role=role, input_tokens=input_t, output_tokens=output_t))


def _build_step_token_usage(token_calls: list[AgentCallTokens]) -> StepTokenUsage | None:
    if not token_calls:
        return None
    total_in = sum(c.input_tokens for c in token_calls)
    total_out = sum(c.output_tokens for c in token_calls)
    return StepTokenUsage(
        agent_calls=token_calls,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
    )


def _aggregate_trajectory_tokens(steps: list[Step]) -> dict[str, Any] | None:
    total_input = 0
    total_output = 0
    per_role: dict[str, dict[str, int]] = {}
    has_any = False
    for step in steps:
        if step.token_usage is None:
            continue
        has_any = True
        total_input += step.token_usage.total_input_tokens
        total_output += step.token_usage.total_output_tokens
        for call in step.token_usage.agent_calls:
            if call.role not in per_role:
                per_role[call.role] = {"input_tokens": 0, "output_tokens": 0}
            per_role[call.role]["input_tokens"] += call.input_tokens
            per_role[call.role]["output_tokens"] += call.output_tokens
    if not has_any:
        return None
    total = total_input + total_output
    estimated_cost = (total_input / 1_000_000 * 3) + (total_output / 1_000_000 * 15)
    return {
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total,
        "estimated_cost_usd": round(estimated_cost, 4),
        "per_role": per_role,
    }


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
) -> AgentInvocationResult | None:
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
) -> AgentInvocationResult | None:
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
    state_schema: dict | None = None,
) -> Step:
    actors = [a for a in scenario.agents if a.role == AgentRole.ACTOR]
    constraint_evaluators = [a for a in scenario.agents if a.role == AgentRole.CONSTRAINT_EVALUATOR]
    resolvers = [a for a in scenario.agents if a.role == AgentRole.RESOLVER]

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
    actor_extra: dict = {}
    if scenario.diversity_lenses:
        actor_extra["diversity_lenses"] = scenario.diversity_lenses

    logger.debug("flat_step.propose_start", step=step_num, n_actors=len(actors))
    t0 = time.monotonic()

    token_calls: list[AgentCallTokens] = []
    actor_results: dict[str, AgentInvocationResult | None] = {}

    async def _run_actor(a):
        prompt = build_prompt(a, step_num, rules, trajectory_id=trajectory_id, **embed_kwargs, **actor_extra)
        result = await _invoke_and_collect(
            a, board.workspace, step_num, prompt, timeout, agent_semaphore, max_concurrent,
        )
        actor_results[a.name] = result

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
        result = actor_results.get(a.name)
        _collect_tokens_from_result(result, a.role.value, token_calls)
        output = result.output if result else None
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

    # Adaptive review: override if state change exceeds threshold
    if scenario.review_threshold is not None and not is_review_step:
        magnitude = board.get_state_delta_magnitude(state_before)
        if magnitude is not None and magnitude > scenario.review_threshold:
            logger.info(
                "step.adaptive_review_triggered",
                step=step_num,
                magnitude=round(magnitude, 4),
                threshold=scenario.review_threshold,
            )
            is_review_step = True

    conflicts = detect_conflicts(proposals)

    critiques = []
    resolution = None

    if is_review_step:
        # PATH C: Full review — constraint evaluator (if defined) then resolver
        if constraint_evaluators:
            proposals_dicts = [p.model_dump() for p in proposals]
            ce_kwargs = {**embed_kwargs, "proposals": proposals_dicts}

            logger.debug("flat_step.evaluate_start", step=step_num, n_evaluators=len(constraint_evaluators))
            t1 = time.monotonic()

            ce_results: dict[str, AgentInvocationResult | None] = {}

            async def _run_constraint_evaluator(c):
                prompt = build_prompt(c, step_num, rules, **ce_kwargs)
                result = await _invoke_and_collect(
                    c, board.workspace, step_num, prompt, timeout, agent_semaphore, max_concurrent,
                )
                ce_results[c.name] = result

            try:
                async with asyncio.TaskGroup() as tg:
                    for c in constraint_evaluators:
                        tg.create_task(_run_constraint_evaluator(c))
            except ExceptionGroup as eg:
                for exc in eg.exceptions:
                    logger.error(
                        "flat_step.evaluate.unhandled_failure", step=step_num, error=str(exc),
                    )
            logger.debug(
                "flat_step.evaluate_done", step=step_num,
                duration_s=round(time.monotonic() - t1, 3),
            )

            for c in constraint_evaluators:
                result = ce_results.get(c.name)
                _collect_tokens_from_result(result, c.role.value, token_calls)
                output = result.output if result else None
                cr = None
                if output:
                    cr = parse_critique_from_text(output, c.name)
                if cr is None:
                    cr = parse_critique(board.workspace, c.name, step_num)
                if cr:
                    critiques.append(cr)
                    board.save_critique(cr, step_num)

        if resolvers:
            logger.debug("flat_step.resolve_start", step=step_num)
            t2 = time.monotonic()
            resolver = resolvers[0]
            resolver_kwargs = {
                **embed_kwargs,
                "proposals": [p.model_dump() for p in proposals],
                "critiques": [c.model_dump() for c in critiques],
                "conflicts": conflicts,
            }
            prompt = build_prompt(resolver, step_num, rules, **resolver_kwargs)
            resolver_result = await _invoke_with_retry_return(
                resolver, board.workspace, step_num, prompt, timeout,
            )
            _collect_tokens_from_result(resolver_result, resolver.role.value, token_calls)
            resolver_output = resolver_result.output if resolver_result else None
            if resolver_output:
                resolution = parse_resolution_from_text(resolver_output)
            if resolution is None:
                resolution = parse_resolution(board.workspace, step_num)
            logger.debug(
                "flat_step.resolve_done", step=step_num,
                duration_s=round(time.monotonic() - t2, 3),
            )

        if resolution is None:
            resolution = _fallback_resolution(proposals)

        if state_schema and resolution.state_delta:
            warnings = validate_state_delta(resolution.state_delta, state_schema)
            if warnings:
                logger.warning("state_delta.validation", step=step_num, warnings=warnings)
                resolution.validation_warnings = warnings

        board.save_resolution(resolution, step_num)
        state_after = board.apply_resolution(resolution, step_num)
        board.set_last_review_state(state_after)

    elif conflicts:
        # PATH B: Conflicts detected — resolver only (no constraint evaluator)
        logger.info(
            "step.conflict_resolution", step=step_num,
            n_conflicts=len(conflicts),
            fields=[c.field for c in conflicts],
        )

        if resolvers:
            logger.debug("flat_step.resolve_start", step=step_num)
            t2 = time.monotonic()
            resolver = resolvers[0]
            resolver_kwargs = {
                **embed_kwargs,
                "proposals": [p.model_dump() for p in proposals],
                "conflicts": conflicts,
            }
            prompt = build_prompt(resolver, step_num, rules, **resolver_kwargs)
            resolver_result = await _invoke_with_retry_return(
                resolver, board.workspace, step_num, prompt, timeout,
            )
            _collect_tokens_from_result(resolver_result, resolver.role.value, token_calls)
            resolver_output = resolver_result.output if resolver_result else None
            if resolver_output:
                resolution = parse_resolution_from_text(resolver_output)
            if resolution is None:
                resolution = parse_resolution(board.workspace, step_num)
            logger.debug(
                "flat_step.resolve_done", step=step_num,
                duration_s=round(time.monotonic() - t2, 3),
            )

        if resolution is None:
            resolution = _fallback_resolution(proposals)

        if state_schema and resolution.state_delta:
            warnings = validate_state_delta(resolution.state_delta, state_schema)
            if warnings:
                logger.warning("state_delta.validation", step=step_num, warnings=warnings)
                resolution.validation_warnings = warnings

        board.save_resolution(resolution, step_num)
        state_after = board.apply_resolution(resolution, step_num)

    else:
        # PATH A: No conflicts, not a review step — auto-merge
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
        token_usage=_build_step_token_usage(token_calls),
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
    state_schema: dict | None = None,
    max_steps: int = 1,
) -> Step:
    rules = scenario.rules
    max_concurrent = scenario.max_concurrent_agents
    proposals = []
    critiques = []
    token_calls: list[AgentCallTokens] = []

    force_entities = [e for e in scenario.entities if e.type == TrajectoryType.FORCE]
    pop_entities = [e for e in scenario.entities if e.type == TrajectoryType.POPULATION]
    ce_entities = [e for e in scenario.entities if e.type == TrajectoryType.CONSTRAINT_EVALUATOR]
    resolver_entities = [e for e in scenario.entities if e.type == TrajectoryType.RESOLVER]

    logger.debug(
        "entity_step.order",
        step=step_num,
        n_forces=len(force_entities),
        n_populations=len(pop_entities),
        n_constraint_evaluators=len(ce_entities),
        n_resolvers=len(resolver_entities),
    )

    current_state = board.read_state()
    narrative_text = _read_narrative(board)
    wildcard_dict = _read_wildcard_dict(board, step_num)
    embed_kwargs: dict = {
        "state": current_state,
        "narrative": narrative_text,
        "wildcard": wildcard_dict,
    }
    actor_extra: dict = {}
    if scenario.diversity_lenses:
        actor_extra["diversity_lenses"] = scenario.diversity_lenses

    # Phase 1: Forces propose world-level changes
    force_agents = [a for e in force_entities for a in e.agents]
    if force_agents:
        logger.debug("entity_step.forces_start", step=step_num, n_agents=len(force_agents))
        t0 = time.monotonic()
        force_results: dict[str, AgentInvocationResult | None] = {}

        async def _run_force(a):
            prompt = build_prompt(a, step_num, rules, trajectory_id=trajectory_id, **embed_kwargs, **actor_extra)
            result = await _invoke_and_collect(
                a, board.workspace, step_num, prompt, timeout, agent_semaphore, max_concurrent,
            )
            force_results[a.name] = result

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
            result = force_results.get(a.name)
            _collect_tokens_from_result(result, a.role.value, token_calls)
            output = result.output if result else None
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
        pop_results: dict[str, AgentInvocationResult | None] = {}

        async def _run_pop(a):
            prompt = build_prompt(
                a, step_num, rules, entity_interaction.get(a.name, ""),
                trajectory_id=trajectory_id, **embed_kwargs, **actor_extra,
            )
            result = await _invoke_and_collect(
                a, board.workspace, step_num, prompt, timeout, agent_semaphore, max_concurrent,
            )
            pop_results[a.name] = result

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
            result = pop_results.get(a.name)
            _collect_tokens_from_result(result, a.role.value, token_calls)
            output = result.output if result else None
            p = None
            if output:
                p = parse_proposal_from_text(output, a.name)
            if p is None:
                p = parse_proposal(board.workspace, a.name, step_num)
            if p:
                proposals.append(p)
                board.save_proposal(p, step_num)

    # Phase 3: Conflict-gated evaluation and resolution
    conflicts = detect_conflicts(proposals)
    is_review_step = (
        scenario.review_interval == 1
        or (step_num % scenario.review_interval == 0)
        or (step_num == max_steps - 1)
    )

    # Adaptive review: override if state change exceeds threshold
    if scenario.review_threshold is not None and not is_review_step:
        magnitude = board.get_state_delta_magnitude(state_before)
        if magnitude is not None and magnitude > scenario.review_threshold:
            logger.info(
                "step.adaptive_review_triggered",
                step=step_num,
                magnitude=round(magnitude, 4),
                threshold=scenario.review_threshold,
            )
            is_review_step = True

    resolution = None

    if is_review_step:
        # PATH C: Full review — constraint evaluators (if defined) then resolver
        ce_agents = [a for e in ce_entities for a in e.agents]
        if ce_agents:
            proposals_dicts = [p.model_dump() for p in proposals]
            ce_kwargs = {**embed_kwargs, "proposals": proposals_dicts}

            logger.debug("entity_step.evaluate_start", step=step_num, n_agents=len(ce_agents))
            t2 = time.monotonic()
            ce_results: dict[str, AgentInvocationResult | None] = {}

            async def _run_constraint_evaluator(c):
                prompt = build_prompt(c, step_num, rules, **ce_kwargs)
                result = await _invoke_and_collect(
                    c, board.workspace, step_num, prompt, timeout, agent_semaphore, max_concurrent,
                )
                ce_results[c.name] = result

            try:
                async with asyncio.TaskGroup() as tg:
                    for c in ce_agents:
                        tg.create_task(_run_constraint_evaluator(c))
            except ExceptionGroup as eg:
                for exc in eg.exceptions:
                    logger.error(
                        "entity_step.evaluate.unhandled_failure", step=step_num, error=str(exc),
                    )
            logger.debug(
                "entity_step.evaluate_done", step=step_num,
                duration_s=round(time.monotonic() - t2, 3),
            )
            for c in ce_agents:
                result = ce_results.get(c.name)
                _collect_tokens_from_result(result, c.role.value, token_calls)
                output = result.output if result else None
                cr = None
                if output:
                    cr = parse_critique_from_text(output, c.name)
                if cr is None:
                    cr = parse_critique(board.workspace, c.name, step_num)
                if cr:
                    critiques.append(cr)
                    board.save_critique(cr, step_num)

        resolver_agents = [a for e in resolver_entities for a in e.agents if a.role == AgentRole.RESOLVER]
        if resolver_agents:
            logger.debug("entity_step.resolve_start", step=step_num)
            t3 = time.monotonic()
            resolver = resolver_agents[0]
            resolver_kwargs = {
                **embed_kwargs,
                "proposals": [p.model_dump() for p in proposals],
                "critiques": [c.model_dump() for c in critiques],
                "conflicts": conflicts,
            }
            prompt = build_prompt(resolver, step_num, rules, **resolver_kwargs)
            resolver_result = await _invoke_with_retry_return(
                resolver, board.workspace, step_num, prompt, timeout,
            )
            _collect_tokens_from_result(resolver_result, resolver.role.value, token_calls)
            resolver_output = resolver_result.output if resolver_result else None
            if resolver_output:
                resolution = parse_resolution_from_text(resolver_output)
            if resolution is None:
                resolution = parse_resolution(board.workspace, step_num)
            logger.debug(
                "entity_step.resolve_done", step=step_num,
                duration_s=round(time.monotonic() - t3, 3),
            )

        if resolution is None:
            resolution = _fallback_resolution(proposals)

        if state_schema and resolution.state_delta:
            warnings = validate_state_delta(resolution.state_delta, state_schema)
            if warnings:
                logger.warning("state_delta.validation", step=step_num, warnings=warnings)
                resolution.validation_warnings = warnings

        board.save_resolution(resolution, step_num)
        state_after = board.apply_resolution(resolution, step_num)
        board.set_last_review_state(state_after)

    elif conflicts:
        # PATH B: Conflicts detected — resolver only
        logger.info(
            "step.conflict_resolution", step=step_num,
            n_conflicts=len(conflicts),
            fields=[c.field for c in conflicts],
        )

        resolver_agents = [a for e in resolver_entities for a in e.agents if a.role == AgentRole.RESOLVER]
        if resolver_agents:
            logger.debug("entity_step.resolve_start", step=step_num)
            t3 = time.monotonic()
            resolver = resolver_agents[0]
            resolver_kwargs = {
                **embed_kwargs,
                "proposals": [p.model_dump() for p in proposals],
                "conflicts": conflicts,
            }
            prompt = build_prompt(resolver, step_num, rules, **resolver_kwargs)
            resolver_result = await _invoke_with_retry_return(
                resolver, board.workspace, step_num, prompt, timeout,
            )
            _collect_tokens_from_result(resolver_result, resolver.role.value, token_calls)
            resolver_output = resolver_result.output if resolver_result else None
            if resolver_output:
                resolution = parse_resolution_from_text(resolver_output)
            if resolution is None:
                resolution = parse_resolution(board.workspace, step_num)
            logger.debug(
                "entity_step.resolve_done", step=step_num,
                duration_s=round(time.monotonic() - t3, 3),
            )

        if resolution is None:
            resolution = _fallback_resolution(proposals)

        if state_schema and resolution.state_delta:
            warnings = validate_state_delta(resolution.state_delta, state_schema)
            if warnings:
                logger.warning("state_delta.validation", step=step_num, warnings=warnings)
                resolution.validation_warnings = warnings

        board.save_resolution(resolution, step_num)
        state_after = board.apply_resolution(resolution, step_num)

    else:
        # PATH A: No conflicts, not a review step — auto-merge
        next_review_step = ((step_num // scenario.review_interval) + 1) * scenario.review_interval
        logger.debug(
            "step.auto_merge", step=step_num,
            n_proposals=len(proposals), next_review_step=next_review_step,
        )

        merged_state = deepcopy(state_before)
        for p in proposals:
            expanded = _expand_dotted_keys(p.proposed_changes)
            _deep_merge(merged_state, expanded)
        board.write_state(merged_state)
        board.snapshot_state(step_num + 1)

        narrative = (
            f"Step {step_num}: Auto-merged {len(proposals)} entity proposals "
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
        token_usage=_build_step_token_usage(token_calls),
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
        narrative="Changes applied from all proposals without resolver arbitration.",
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
