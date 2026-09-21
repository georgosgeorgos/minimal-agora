"""Tests for multi-step LLM batching."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from minimal_agora.agents import get_default_provider, set_default_provider
from minimal_agora.batching import build_batch_prompt, parse_batch_output
from minimal_agora.loop import run_trajectory
from minimal_agora.models import (
    AgentConfig,
    AgentRole,
    BatchCritique,
    BatchCritiqueStep,
    BatchProposal,
    BatchProposalStep,
    BatchResolution,
    BatchResolutionStep,
    EntityConfig,
    Scenario,
    SimMode,
    StepBatchingConfig,
    StepExecutionMode,
    TrajectoryType,
)
from minimal_agora.providers.protocol import AgentInvocationResult
from minimal_agora.scenario import setup_workspace


class BatchMockProvider:
    def __init__(self, *, invalid_resolver: bool = False) -> None:
        self.call_count = 0
        self.invalid_resolver = invalid_resolver

    async def invoke(
        self,
        prompt: str,
        workspace: Path,
        timeout: int = 300,
        model: str | None = None,
        temperature: float | None = None,
    ) -> AgentInvocationResult:
        self.call_count += 1
        match = re.search(r"Simulate Steps (\d+)-(\d+)", prompt)
        assert match is not None
        start, end = (int(value) for value in match.groups())

        if "batch actor agent" in prompt:
            payload = BatchProposal(
                steps=[
                    BatchProposalStep(
                        step_number=step,
                        agent="actor",
                        role=AgentRole.ACTOR,
                        proposed_changes={"value": step + 1},
                        reasoning="advance",
                    )
                    for step in range(start, end + 1)
                ],
            )
        elif "batch constraint evaluator agent" in prompt:
            payload = BatchCritique(
                steps=[
                    BatchCritiqueStep(
                        step_number=step,
                        agent="critic",
                        target_proposals=["actor"],
                        assessment="plausible",
                        plausibility=0.9,
                    )
                    for step in range(start, end + 1)
                ],
            )
        else:
            assert "batch resolver agent" in prompt
            if self.invalid_resolver:
                return AgentInvocationResult(output="not json", model="batch-mock")
            payload = BatchResolution(
                steps=[
                    BatchResolutionStep(
                        step_number=step,
                        state_delta={"value": step + 1},
                        narrative=f"Step {step} advanced.",
                        reasoning="resolved",
                    )
                    for step in range(start, end + 1)
                ],
            )

        output = payload.model_dump_json()
        return AgentInvocationResult(
            output=output,
            tokens_used=30,
            input_tokens=20,
            output_tokens=10,
            model="batch-mock",
        )


def _scenario(**overrides) -> Scenario:
    values = {
        "name": "batch-test",
        "mode": SimMode.COUNTERFACTUAL,
        "initial_state": {"value": 0},
        "step_budget": 4,
        "step_batching": StepBatchingConfig(batch_size=3),
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


def test_step_batching_default_disabled():
    scenario = Scenario(
        name="test",
        mode=SimMode.COUNTERFACTUAL,
        initial_state={"value": 0},
    )
    assert scenario.step_batching is None


def test_step_batch_size_must_exceed_one():
    with pytest.raises(ValidationError):
        StepBatchingConfig(batch_size=1)


@pytest.mark.parametrize(
    "overrides",
    [
        {"adaptive_steps": {"reasoning_interval": 3}},
        {"wildcards_enabled": True},
        {"resampling": {"interval": 2}},
        {
            "mode": SimMode.POPULATION,
            "entities": [
                EntityConfig(name="population", type=TrajectoryType.POPULATION),
            ],
        },
    ],
)
def test_step_batching_rejects_unsupported_combinations(overrides: dict):
    with pytest.raises(ValidationError, match="step_batching"):
        _scenario(**overrides)


def test_batch_prompt_and_parser_roundtrip():
    agent = AgentConfig(role=AgentRole.ACTOR, name="actor", perspective="advance")
    prompt = build_batch_prompt(
        agent,
        step_numbers=[2, 3, 4],
        rules=[],
        state={"value": 2},
        narrative="Earlier events.",
        trajectory_id=0,
    )
    payload = BatchProposal(
        steps=[
            BatchProposalStep(
                step_number=step,
                agent="actor",
                role=AgentRole.ACTOR,
                proposed_changes={"value": step + 1},
            )
            for step in [2, 3, 4]
        ],
    )

    assert "Simulate Steps 2-4" in prompt
    assert json.dumps({"value": 2}, indent=2) in prompt
    assert parse_batch_output(AgentRole.ACTOR, payload.model_dump_json()) == payload
    assert (
        parse_batch_output(
            AgentRole.ACTOR,
            f"```json\n{payload.model_dump_json()}\n```",
        )
        == payload
    )


def test_run_trajectory_batches_provider_calls_and_checkpoints(tmp_path: Path):
    scenario = _scenario()
    provider = BatchMockProvider()
    original = get_default_provider()
    set_default_provider(provider)

    try:
        workspace = setup_workspace(scenario, tmp_path, trajectory_id=0)
        trajectory = asyncio.run(run_trajectory(scenario, workspace))
    finally:
        set_default_provider(original)

    assert provider.call_count == 6  # 3 roles x 2 batches, instead of 3 x 4 steps
    assert len(trajectory.steps) == 4
    assert [step.state_after["value"] for step in trajectory.steps] == [1, 2, 3, 4]
    assert all(step.execution_mode == StepExecutionMode.BATCHED for step in trajectory.steps)
    assert [step.batch_start_step for step in trajectory.steps] == [0, 0, 0, 3]
    assert all((workspace / "history" / f"step_{step:03d}_full.json").exists() for step in range(4))
    assert trajectory.total_tokens is not None
    assert trajectory.total_tokens["total_tokens"] == 180
    assert trajectory.metadata["step_batching"] == {
        "batches": 2,
        "batched_steps": 4,
        "per_agent_step_calls_avoided": 2,
    }


def test_batched_trajectory_stops_at_intermediate_termination(tmp_path: Path):
    scenario = _scenario(
        termination={
            "max_steps": 4,
            "conditions": [{"field": "value", "greater_than": 1}],
        },
    )
    provider = BatchMockProvider()
    original = get_default_provider()
    set_default_provider(provider)

    try:
        workspace = setup_workspace(scenario, tmp_path, trajectory_id=0)
        trajectory = asyncio.run(run_trajectory(scenario, workspace))
    finally:
        set_default_provider(original)

    assert len(trajectory.steps) == 2
    assert trajectory.outcome is not None
    assert trajectory.outcome.final_step == 1
    assert trajectory.outcome.final_state["value"] == 2
    assert not (workspace / "history" / "step_002_full.json").exists()


def test_invalid_batch_resolution_falls_back_to_actor_proposals(tmp_path: Path):
    scenario = _scenario(step_budget=3)
    provider = BatchMockProvider(invalid_resolver=True)
    original = get_default_provider()
    set_default_provider(provider)

    try:
        workspace = setup_workspace(scenario, tmp_path, trajectory_id=0)
        trajectory = asyncio.run(run_trajectory(scenario, workspace))
    finally:
        set_default_provider(original)

    assert [step.state_after["value"] for step in trajectory.steps] == [1, 2, 3]
    assert all(step.resolution is not None for step in trajectory.steps)
    assert all(
        "without resolver arbitration" in step.resolution.narrative
        for step in trajectory.steps
        if step.resolution is not None
    )
