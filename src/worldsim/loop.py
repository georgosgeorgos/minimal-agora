from __future__ import annotations

import asyncio
import random
from copy import deepcopy
from pathlib import Path

from worldsim.agents import (
    build_prompt,
    invoke_agent,
    parse_critique,
    parse_proposal,
    parse_resolution,
)
from worldsim.board import Board
from worldsim.models import (
    AgentRole,
    Resolution,
    Scenario,
    Step,
    Trajectory,
    TrajectoryOutcome,
    TrajectoryType,
    WildcardEvent,
)


async def run_trajectory(
    scenario: Scenario,
    workspace: Path,
    trajectory_id: int = 0,
    agent_timeout: int = 300,
) -> Trajectory:
    board = Board(workspace)
    trajectory = Trajectory(
        scenario_name=scenario.name,
        trajectory_id=trajectory_id,
    )

    max_steps = scenario.termination.get("max_steps", scenario.step_budget)
    conditions = scenario.termination.get("conditions", [])

    for step_num in range(max_steps):
        wildcard = _roll_wildcard(scenario.wildcards)
        if wildcard:
            print(f"  [trajectory {trajectory_id}] step {step_num}/{max_steps} — WILDCARD: {wildcard.name}")
            board.write_wildcard(wildcard, step_num)
        else:
            print(f"  [trajectory {trajectory_id}] step {step_num}/{max_steps}")
            board.clear_wildcard(step_num)

        step = await _run_step(scenario, board, step_num, agent_timeout)
        trajectory.steps.append(step)

        if _check_termination(step.state_after, conditions):
            print(f"  [trajectory {trajectory_id}] terminated at step {step_num}")
            break

    final_state = board.read_state()
    final_step = len(trajectory.steps) - 1

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
) -> Step:
    state_before = deepcopy(board.read_state())

    if scenario.entities:
        return await _run_entity_step(scenario, board, step_num, timeout, state_before)
    return await _run_flat_step(scenario, board, step_num, timeout, state_before)


async def _run_flat_step(
    scenario: Scenario,
    board: Board,
    step_num: int,
    timeout: int,
    state_before: dict,
) -> Step:
    actors = [a for a in scenario.agents if a.role == AgentRole.ACTOR]
    critics = [a for a in scenario.agents if a.role == AgentRole.CRITIC]
    judges = [a for a in scenario.agents if a.role == AgentRole.JUDGE]

    rules = scenario.rules
    actor_tasks = [
        invoke_agent(a, board.workspace, step_num, build_prompt(a, step_num, rules), timeout)
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
            invoke_agent(c, board.workspace, step_num, build_prompt(c, step_num, rules), timeout)
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
        await invoke_agent(judge, board.workspace, step_num, build_prompt(judge, step_num, rules), timeout)
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
) -> Step:
    rules = scenario.rules
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
            invoke_agent(a, board.workspace, step_num, build_prompt(a, step_num, rules), timeout)
            for a in force_agents
        ]
        await asyncio.gather(*force_tasks, return_exceptions=True)
        for a in force_agents:
            p = parse_proposal(board.workspace, a.name, step_num)
            if p:
                proposals.append(p)
                board.save_proposal(p, step_num)

    # Phase 2: Populations propose their changes (in parallel)
    pop_agents = [a for e in pop_entities for a in e.agents]
    if pop_agents:
        pop_tasks = [
            invoke_agent(a, board.workspace, step_num, build_prompt(a, step_num, rules), timeout)
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
            invoke_agent(c, board.workspace, step_num, build_prompt(c, step_num, rules), timeout)
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
        await invoke_agent(judge, board.workspace, step_num, build_prompt(judge, step_num, rules), timeout)
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
    merged = {}
    reasoning_parts = []
    for p in proposals:
        merged.update(p.proposed_changes)
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


def _roll_wildcard(wildcards: list[WildcardEvent]) -> WildcardEvent | None:
    for event in wildcards:
        if random.random() < event.probability:
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


def _save_trajectory(trajectory: Trajectory, workspace: Path) -> None:
    path = workspace / "trajectory.json"
    with open(path, "w") as f:
        f.write(trajectory.model_dump_json(indent=2))
