"""Integration tests exercising run_trajectory() and run_batch() with MockProvider."""
from __future__ import annotations

import asyncio
import re
from collections.abc import Generator
from pathlib import Path

import pytest

from minimal_agora.agents import get_default_provider, set_default_provider
from minimal_agora.analysis import aggregate_outcomes
from minimal_agora.loop import run_trajectory
from minimal_agora.models import (
    AgentConfig,
    AgentRole,
    Critique,
    EntityConfig,
    OutcomeClass,
    OutcomeConfig,
    Proposal,
    Resolution,
    Scenario,
    SimMode,
    TerminationCondition,
    TrajectoryType,
)
from minimal_agora.providers.protocol import AgentInvocationResult
from minimal_agora.runner import run_batch
from minimal_agora.scenario import setup_workspace

pytestmark = pytest.mark.integration


class FileWritingMockProvider:
    """Mock provider that writes proposal/critique/resolution JSON files to disk,
    mimicking how the real subprocess provider operates."""

    def __init__(self) -> None:
        self.call_count: int = 0

    async def invoke(
        self, prompt: str, workspace: Path, timeout: int = 300,
    ) -> AgentInvocationResult:
        self.call_count += 1

        name_match = re.search(r"You are \*\*(\w+)\*\*", prompt)
        agent_name = name_match.group(1) if name_match else "unknown"

        step_match = re.search(r"step_(\d{3})", prompt)
        step_num = int(step_match.group(1)) if step_match else 0

        if "an actor agent" in prompt:
            proposal = Proposal(
                agent=agent_name,
                role=AgentRole.ACTOR,
                proposed_changes={"time": {"step": step_num + 1}},
                reasoning=f"Mock evolution at step {step_num}",
                confidence=0.8,
            )
            path = workspace / "proposals" / f"step_{step_num:03d}_{agent_name}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(proposal.model_dump_json(indent=2))

        elif "a critic agent" in prompt:
            critique = Critique(
                agent=agent_name,
                target_proposals=[agent_name],
                assessment="Plausible mock changes",
                plausibility=0.85,
                issues=[],
            )
            path = workspace / "critiques" / f"step_{step_num:03d}_{agent_name}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(critique.model_dump_json(indent=2))

        elif "the judge agent" in prompt:
            resolution = Resolution(
                state_delta={"time": {"step": step_num + 1}},
                narrative=f"Step {step_num}: Mock changes applied.",
                reasoning="All proposals deemed plausible.",
            )
            path = workspace / "resolutions" / f"step_{step_num:03d}_resolution.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(resolution.model_dump_json(indent=2))

        return AgentInvocationResult(output="mock", tokens_used=100, model="mock-model")


@pytest.fixture()
def mock_provider() -> Generator[FileWritingMockProvider]:
    """Set FileWritingMockProvider as default and restore original after test."""
    original = get_default_provider()
    provider = FileWritingMockProvider()
    set_default_provider(provider)
    yield provider
    set_default_provider(original)


def _counterfactual_scenario() -> Scenario:
    return Scenario(
        name="test-counterfactual",
        mode=SimMode.COUNTERFACTUAL,
        step_budget=2,
        initial_state={"time": {"step": 0}, "value": 1},
        agents=[
            AgentConfig(role=AgentRole.ACTOR, name="actor_1", perspective="Test actor"),
            AgentConfig(role=AgentRole.CRITIC, name="critic_1", perspective="Test critic"),
            AgentConfig(role=AgentRole.JUDGE, name="judge_1", perspective="Test judge"),
        ],
        termination={"max_steps": 2},
        outcome=OutcomeConfig(
            question="Did the simulation complete?",
            classifier=[
                OutcomeClass(
                    name="completed",
                    condition=TerminationCondition(field="time.step", greater_than=0),
                ),
                OutcomeClass(name="incomplete", default=True),
            ],
        ),
    )


def _population_scenario() -> Scenario:
    return Scenario(
        name="test-population",
        mode=SimMode.POPULATION,
        step_budget=2,
        initial_state={"time": {"step": 0}},
        entities=[
            EntityConfig(
                name="env",
                type=TrajectoryType.FORCE,
                agents=[
                    AgentConfig(
                        role=AgentRole.ACTOR, name="env_force",
                        perspective="Environmental forces",
                    ),
                ],
            ),
            EntityConfig(
                name="pop_a",
                type=TrajectoryType.POPULATION,
                state_prefix="pops.a",
                initial_state={"count": 100},
                agents=[
                    AgentConfig(
                        role=AgentRole.ACTOR, name="pop_a_actor",
                        perspective="Population A evolution",
                    ),
                ],
                can_interact_with=["pop_b"],
            ),
            EntityConfig(
                name="pop_b",
                type=TrajectoryType.POPULATION,
                state_prefix="pops.b",
                initial_state={"count": 50},
                agents=[
                    AgentConfig(
                        role=AgentRole.ACTOR, name="pop_b_actor",
                        perspective="Population B evolution",
                    ),
                ],
                can_interact_with=["pop_a"],
            ),
            EntityConfig(
                name="critic_ent",
                type=TrajectoryType.CRITIC,
                agents=[
                    AgentConfig(
                        role=AgentRole.CRITIC, name="balance_critic",
                        perspective="Check ecological balance",
                    ),
                ],
            ),
            EntityConfig(
                name="eval_ent",
                type=TrajectoryType.EVALUATOR,
                agents=[
                    AgentConfig(
                        role=AgentRole.JUDGE, name="world_judge",
                        perspective="Resolve all proposed changes",
                    ),
                ],
            ),
        ],
        termination={"max_steps": 2},
    )


def test_counterfactual_trajectory(
    mock_provider: FileWritingMockProvider, tmp_path: Path,
) -> None:
    """End-to-end counterfactual trajectory completes with correct state updates."""
    scenario = _counterfactual_scenario()
    workspace = setup_workspace(scenario, tmp_path, trajectory_id=0)

    trajectory = asyncio.run(run_trajectory(scenario, workspace, trajectory_id=0))

    assert len(trajectory.steps) == 2
    assert trajectory.outcome is not None
    assert trajectory.outcome.classification == "completed"
    assert trajectory.outcome.final_step == 1

    for step in trajectory.steps:
        assert len(step.proposals) >= 1
        assert len(step.critiques) >= 1
        assert step.resolution is not None
        assert step.state_after["time"]["step"] > step.state_before["time"]["step"]

    assert (workspace / "trajectory.json").exists()
    assert (workspace / "history" / "step_000_full.json").exists()
    assert (workspace / "history" / "step_001_full.json").exists()

    # 2 steps × (1 actor + 1 critic + 1 judge)
    assert mock_provider.call_count == 6


def test_population_trajectory(
    mock_provider: FileWritingMockProvider, tmp_path: Path,
) -> None:
    """End-to-end population trajectory with entity interactions."""
    scenario = _population_scenario()
    workspace = setup_workspace(scenario, tmp_path, trajectory_id=0)

    trajectory = asyncio.run(run_trajectory(scenario, workspace, trajectory_id=0))

    assert len(trajectory.steps) == 2
    assert trajectory.outcome is not None

    for step in trajectory.steps:
        # 1 force + 2 population actors = 3 proposals per step
        assert len(step.proposals) >= 3
        assert len(step.critiques) >= 1
        assert step.resolution is not None

    assert (workspace / "trajectory.json").exists()
    # 2 steps × (1 force + 2 pop + 1 critic + 1 judge)
    assert mock_provider.call_count == 10


def test_batch_run_with_aggregation(
    mock_provider: FileWritingMockProvider, tmp_path: Path,
) -> None:
    """Batch run of 2 trajectories produces aggregate results."""
    scenario = _counterfactual_scenario().model_copy(update={"n_trajectories": 2})

    results = asyncio.run(run_batch(scenario, tmp_path, concurrency=2))

    assert len(results) == 2
    for traj in results:
        assert traj.outcome is not None
        assert len(traj.steps) == 2

    agg = aggregate_outcomes(results, question="Did the simulation complete?")
    assert agg.n_trajectories == 2
    assert agg.scenario_name == "test-counterfactual"
    assert "completed" in agg.outcomes
    assert agg.outcomes["completed"] == 2
