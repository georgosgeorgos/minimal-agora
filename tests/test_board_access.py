"""Tests for embedded and workspace-file board access modes."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from minimal_agora.agents import get_default_provider, set_default_provider
from minimal_agora.board_access import ensure_provider_supports_board_access
from minimal_agora.loop import run_trajectory
from minimal_agora.models import (
    AgentConfig,
    AgentRole,
    BoardAccessMode,
    Critique,
    EntityConfig,
    Proposal,
    Resolution,
    Scenario,
    SimMode,
    TrajectoryType,
)
from minimal_agora.providers.mock import MockProvider
from minimal_agora.providers.protocol import AgentInvocationResult
from minimal_agora.providers.subprocess_provider import ClaudeSubprocessProvider
from minimal_agora.scenario import setup_workspace


class FileBoardProvider:
    supports_workspace_io = True

    def __init__(self) -> None:
        self.call_count = 0
        self.prompts: list[str] = []

    async def invoke(
        self,
        prompt: str,
        workspace: Path,
        timeout: int = 300,
        model: str | None = None,
        temperature: float | None = None,
    ) -> AgentInvocationResult:
        self.call_count += 1
        self.prompts.append(prompt)
        name_match = re.search(r"You are \*\*(\w+)\*\*", prompt)
        step_match = re.search(r"step_(\d{3})", prompt)
        assert name_match is not None
        assert step_match is not None
        name = name_match.group(1)
        step = int(step_match.group(1))

        if "an actor agent" in prompt:
            proposal = Proposal(
                agent=name,
                role=AgentRole.ACTOR,
                proposed_changes={"value": step + 1},
                reasoning="file-backed proposal",
            )
            path = workspace / "proposals" / f"step_{step:03d}_{name}.json"
            path.write_text(proposal.model_dump_json())
        elif "a constraint evaluator agent" in prompt:
            critique = Critique(
                agent=name,
                target_proposals=["actor"],
                assessment="plausible",
                plausibility=0.9,
            )
            path = workspace / "critiques" / f"step_{step:03d}_{name}.json"
            path.write_text(critique.model_dump_json())
        elif "the resolver agent" in prompt:
            resolution = Resolution(
                state_delta={"value": step + 1},
                narrative=f"File-backed step {step}.",
                reasoning="resolved",
            )
            path = workspace / "resolutions" / f"step_{step:03d}_resolution.json"
            path.write_text(resolution.model_dump_json())

        return AgentInvocationResult(output='{"ignored":"in file mode"}', model="file-mock")


def _flat_scenario(**overrides) -> Scenario:
    values = {
        "name": "file-board-test",
        "mode": SimMode.COUNTERFACTUAL,
        "initial_state": {"value": 0},
        "step_budget": 2,
        "board_access": BoardAccessMode.FILES,
        "agents": [
            AgentConfig(role=AgentRole.ACTOR, name="actor", perspective="advance"),
            AgentConfig(
                role=AgentRole.CONSTRAINT_EVALUATOR,
                name="critic",
                perspective="check",
            ),
            AgentConfig(role=AgentRole.RESOLVER, name="resolver", perspective="resolve"),
        ],
    }
    values.update(overrides)
    return Scenario(**values)


def test_board_access_defaults_to_embedded():
    scenario = Scenario(
        name="test",
        mode=SimMode.COUNTERFACTUAL,
        initial_state={"value": 0},
    )
    assert scenario.board_access == BoardAccessMode.EMBEDDED


def test_file_board_access_rejects_step_batching():
    with pytest.raises(ValidationError, match="step_batching"):
        _flat_scenario(step_batching={"batch_size": 3})


def test_file_board_access_requires_workspace_provider(tmp_path: Path):
    scenario = _flat_scenario()
    original = get_default_provider()
    set_default_provider(MockProvider())

    try:
        workspace = setup_workspace(scenario, tmp_path, trajectory_id=0)
        with pytest.raises(RuntimeError, match="workspace I/O"):
            asyncio.run(run_trajectory(scenario, workspace))
    finally:
        set_default_provider(original)


def test_subprocess_provider_supports_workspace_io():
    assert ClaudeSubprocessProvider.supports_workspace_io is True


def test_file_board_access_rejects_insufficient_provider_turns():
    provider = ClaudeSubprocessProvider(max_turns=1)

    with pytest.raises(RuntimeError, match="at least 3 turns"):
        ensure_provider_supports_board_access(BoardAccessMode.FILES, provider)


def test_flat_file_board_mode_uses_artifacts_not_stdout(tmp_path: Path):
    scenario = _flat_scenario()
    provider = FileBoardProvider()
    original = get_default_provider()
    set_default_provider(provider)

    try:
        workspace = setup_workspace(scenario, tmp_path, trajectory_id=0)
        trajectory = asyncio.run(run_trajectory(scenario, workspace))
    finally:
        set_default_provider(original)

    assert provider.call_count == 6
    assert [step.state_after["value"] for step in trajectory.steps] == [1, 2]
    assert all("Read the current world state from" in prompt for prompt in provider.prompts)
    assert all("## Current World State" not in prompt for prompt in provider.prompts)


def test_population_file_board_mode_uses_same_access_policy(tmp_path: Path):
    scenario = Scenario(
        name="population-file-board-test",
        mode=SimMode.POPULATION,
        initial_state={"value": 0},
        step_budget=1,
        board_access=BoardAccessMode.FILES,
        entities=[
            EntityConfig(
                name="environment",
                type=TrajectoryType.FORCE,
                agents=[
                    AgentConfig(
                        role=AgentRole.ACTOR,
                        name="force_actor",
                        perspective="advance",
                    ),
                ],
            ),
            EntityConfig(
                name="arbiter",
                type=TrajectoryType.RESOLVER,
                agents=[
                    AgentConfig(
                        role=AgentRole.RESOLVER,
                        name="resolver",
                        perspective="resolve",
                    ),
                ],
            ),
        ],
    )
    provider = FileBoardProvider()
    original = get_default_provider()
    set_default_provider(provider)

    try:
        workspace = setup_workspace(scenario, tmp_path, trajectory_id=0)
        trajectory = asyncio.run(run_trajectory(scenario, workspace))
    finally:
        set_default_provider(original)

    assert len(trajectory.steps) == 1
    assert trajectory.steps[0].state_after["value"] == 1
    assert all("## Current World State" not in prompt for prompt in provider.prompts)
