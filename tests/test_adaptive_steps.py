"""Tests for adaptive step execution and deterministic routine steps."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from minimal_agora.adaptive import extrapolate_numeric_state, should_reason
from minimal_agora.agents import get_default_provider, set_default_provider
from minimal_agora.loop import run_trajectory
from minimal_agora.models import (
    AdaptiveStepConfig,
    AgentConfig,
    AgentRole,
    Proposal,
    Scenario,
    SimMode,
    Step,
    StepExecutionMode,
)
from minimal_agora.providers.mock import MockProvider
from minimal_agora.scenario import setup_workspace


def _reasoned_step(before: dict, after: dict, step_number: int = 0) -> Step:
    return Step(
        step_number=step_number,
        state_before=before,
        state_after=after,
        execution_mode=StepExecutionMode.REASONED,
    )


def test_adaptive_steps_default_disabled():
    scenario = Scenario(
        name="test",
        mode=SimMode.COUNTERFACTUAL,
        initial_state={"value": 0},
    )
    assert scenario.adaptive_steps is None


def test_adaptive_step_config_rejects_single_step_interval():
    with pytest.raises(ValidationError):
        AdaptiveStepConfig(reasoning_interval=1)


def test_extrapolate_numeric_state_repeats_last_reasoned_delta():
    source = _reasoned_step(
        {"population": {"size": 10, "rate": 1.5}, "phase": "early"},
        {"population": {"size": 12, "rate": 2.0}, "phase": "middle"},
    )

    result = extrapolate_numeric_state(
        {"population": {"size": 14, "rate": 2.5}, "phase": "middle"},
        source,
    )

    assert result == {
        "population": {"size": 16, "rate": 3.0},
        "phase": "middle",
    }


def test_extrapolate_numeric_state_ignores_booleans_and_shape_changes():
    source = _reasoned_step(
        {"value": 1, "active": False},
        {"value": 3, "active": True, "new_field": 10},
    )

    result = extrapolate_numeric_state(
        {"value": 5, "active": True, "new_field": 10},
        source,
    )

    assert result == {"value": 7, "active": True, "new_field": 10}


@pytest.mark.parametrize(
    ("step_num", "max_steps", "wildcard_active", "current_state", "expected"),
    [
        (0, 10, False, {"value": 1}, True),
        (1, 10, True, {"value": 1}, True),
        (5, 10, False, {"value": 1}, True),
        (9, 10, False, {"value": 1}, True),
        (1, 10, False, {"value": 1}, False),
        (1, 10, False, {"value": 2}, True),
    ],
)
def test_should_reason_at_inflection_points(
    step_num: int,
    max_steps: int,
    wildcard_active: bool,
    current_state: dict,
    expected: bool,
):
    config = AdaptiveStepConfig(reasoning_interval=5, change_threshold=0.5)
    previous = _reasoned_step({"value": 0}, {"value": 1})

    assert should_reason(
        config,
        step_num=step_num,
        max_steps=max_steps,
        current_state=current_state,
        last_reasoned_step=previous,
        wildcard_active=wildcard_active,
    ) is expected


def test_run_trajectory_skips_llm_on_routine_steps(tmp_path: Path):
    scenario = Scenario(
        name="adaptive-test",
        mode=SimMode.COUNTERFACTUAL,
        initial_state={"value": 0},
        step_budget=5,
        review_interval=3,
        adaptive_steps=AdaptiveStepConfig(reasoning_interval=3),
        agents=[
            AgentConfig(role=AgentRole.ACTOR, name="actor", perspective="test"),
        ],
    )
    responses = {
        f"Simulation Step {step}": Proposal(
            agent="actor",
            role=AgentRole.ACTOR,
            proposed_changes={"value": step + 1},
            reasoning="test",
        ).model_dump_json()
        for step in range(5)
    }
    provider = MockProvider(responses=responses)
    original = get_default_provider()
    set_default_provider(provider)

    try:
        workspace = setup_workspace(scenario, tmp_path, trajectory_id=0)
        trajectory = asyncio.run(run_trajectory(scenario, workspace))
    finally:
        set_default_provider(original)

    assert provider.call_count == 3
    assert [step.execution_mode for step in trajectory.steps] == [
        StepExecutionMode.REASONED,
        StepExecutionMode.ROUTINE,
        StepExecutionMode.ROUTINE,
        StepExecutionMode.REASONED,
        StepExecutionMode.REASONED,
    ]
    assert [step.state_after["value"] for step in trajectory.steps] == [1, 2, 3, 4, 5]
    assert trajectory.metadata["adaptive_steps"] == {
        "reasoned_steps": 3,
        "routine_steps": 2,
        "llm_steps_skipped": 2,
    }
