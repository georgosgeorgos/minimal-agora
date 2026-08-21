"""Tests for adaptive review interval (review_threshold)."""

import asyncio
import tempfile
from copy import deepcopy
from pathlib import Path

from minimal_agora.board import Board, _flatten_state, compute_state_delta_magnitude
from minimal_agora.models import (
    AgentConfig,
    AgentRole,
    Proposal,
    Scenario,
    SimMode,
)

# ---- Unit tests for _flatten_state ----

def test_flatten_state_simple():
    state = {"a": 1, "b": 2.0}
    flat = _flatten_state(state)
    assert flat == {"a": 1.0, "b": 2.0}


def test_flatten_state_nested():
    state = {"x": {"y": 10, "z": {"w": 20}}, "q": 5}
    flat = _flatten_state(state)
    assert flat == {"x.y": 10.0, "x.z.w": 20.0, "q": 5.0}


def test_flatten_state_skips_non_numeric():
    state = {"a": 1, "b": "text", "c": True, "d": [1, 2], "e": None}
    flat = _flatten_state(state)
    assert flat == {"a": 1.0}


def test_flatten_state_empty():
    assert _flatten_state({}) == {}


# ---- Unit tests for compute_state_delta_magnitude ----

def test_delta_magnitude_identical_states():
    state = {"a": 10, "b": {"c": 20}}
    assert compute_state_delta_magnitude(state, state) == 0.0


def test_delta_magnitude_simple_change():
    before = {"a": 10.0, "b": 20.0}
    after = {"a": 15.0, "b": 20.0}
    # field a: abs(15-10)/max(10,1) = 0.5
    # field b: abs(20-20)/max(20,1) = 0.0
    # mean = 0.25
    result = compute_state_delta_magnitude(before, after)
    assert abs(result - 0.25) < 1e-9


def test_delta_magnitude_nested():
    before = {"x": {"y": 100.0}, "z": 50.0}
    after = {"x": {"y": 200.0}, "z": 50.0}
    # x.y: abs(200-100)/max(100,1) = 1.0
    # z: abs(50-50)/max(50,1) = 0.0
    # mean = 0.5
    result = compute_state_delta_magnitude(before, after)
    assert abs(result - 0.5) < 1e-9


def test_delta_magnitude_zero_before_uses_floor():
    before = {"a": 0.0}
    after = {"a": 5.0}
    # abs(5-0)/max(0,1) = 5.0
    result = compute_state_delta_magnitude(before, after)
    assert abs(result - 5.0) < 1e-9


def test_delta_magnitude_no_shared_numeric():
    before = {"a": "text"}
    after = {"b": 10}
    result = compute_state_delta_magnitude(before, after)
    assert result == 0.0


def test_delta_magnitude_extra_fields_ignored():
    """Fields present in only one state are ignored (only shared keys matter)."""
    before = {"a": 10.0, "b": 20.0}
    after = {"a": 15.0, "c": 100.0}
    # only shared key is "a": abs(15-10)/max(10,1) = 0.5
    result = compute_state_delta_magnitude(before, after)
    assert abs(result - 0.5) < 1e-9


# ---- Board integration tests ----

def test_board_last_review_state_initially_none():
    with tempfile.TemporaryDirectory() as tmpdir:
        board = Board(Path(tmpdir))
        assert board.get_state_delta_magnitude({"a": 1}) is None


def test_board_set_and_get_delta():
    with tempfile.TemporaryDirectory() as tmpdir:
        board = Board(Path(tmpdir))
        board.set_last_review_state({"a": 10.0, "b": 20.0})
        mag = board.get_state_delta_magnitude({"a": 15.0, "b": 20.0})
        assert mag is not None
        assert abs(mag - 0.25) < 1e-9


def test_board_set_review_state_is_deep_copy():
    """Mutating the original dict should not affect the stored review state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        board = Board(Path(tmpdir))
        original = {"a": 10.0}
        board.set_last_review_state(original)
        original["a"] = 999.0
        mag = board.get_state_delta_magnitude({"a": 10.0})
        assert mag == 0.0


# ---- Scenario model tests ----

def test_review_threshold_default_none():
    scenario = Scenario(
        name="test", mode=SimMode.COUNTERFACTUAL,
        initial_state={"x": 0}, step_budget=5,
    )
    assert scenario.review_threshold is None


def test_review_threshold_configurable():
    scenario = Scenario(
        name="test", mode=SimMode.COUNTERFACTUAL,
        initial_state={"x": 0}, step_budget=5,
        review_threshold=0.3,
    )
    assert scenario.review_threshold == 0.3


# ---- Integration test: adaptive review triggers mid-interval ----

def test_adaptive_review_triggers_on_large_state_change():
    """With review_interval=5 and review_threshold=0.1, a large state change
    at step 1 should trigger a review (resolution is not None), even though
    the fixed interval would skip it."""
    from minimal_agora.loop import _run_flat_step
    from minimal_agora.scenario import setup_workspace

    scenario = Scenario(
        name="test", mode=SimMode.COUNTERFACTUAL,
        initial_state={"value": 10.0, "other": 5.0},
        step_budget=10,
        review_interval=5,
        review_threshold=0.1,
        agents=[
            AgentConfig(role=AgentRole.ACTOR, name="actor_a", perspective="test"),
            AgentConfig(role=AgentRole.RESOLVER, name="resolver_a", perspective="test"),
        ],
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = setup_workspace(scenario, Path(tmpdir), trajectory_id=0)
        board = Board(workspace)
        semaphore = asyncio.Semaphore(8)

        import minimal_agora.loop as loop_module

        call_log = []

        def _write_mock_proposal(agent, workspace, step_num):
            if step_num == 1:
                changes = {"value": 50.0}  # large change from 10 -> 50
            else:
                changes = {"value": step_num + 10}
            proposal = Proposal(
                agent=agent.name, role=AgentRole.ACTOR,
                proposed_changes=changes,
                reasoning="test",
            )
            path = workspace / "proposals" / f"step_{step_num:03d}_{agent.name}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                f.write(proposal.model_dump_json(indent=2))

        async def mock_invoke(agent, workspace, step_num, prompt, timeout, max_retries=1, temperature=None):
            call_log.append((agent.name, agent.role.value, step_num))
            if agent.role == AgentRole.ACTOR:
                _write_mock_proposal(agent, workspace, step_num)

        original = loop_module._invoke_with_retry_return
        loop_module._invoke_with_retry_return = mock_invoke

        try:
            max_steps = 10

            # Step 0: review step (0 % 5 == 0), establishes last_review_state
            state_before_0 = deepcopy(board.read_state())
            step0 = asyncio.run(_run_flat_step(
                scenario, board, 0, 60, state_before_0,
                trajectory_id=0, agent_semaphore=semaphore, max_steps=max_steps,
            ))
            assert step0.resolution is not None, "Step 0 should be a review step"

            # Step 1: normally NOT a review step (1 % 5 != 0, not last step)
            # But proposal changes value from ~10 to 50 => delta > 0.1
            # However, the adaptive check runs BEFORE proposals are gathered --
            # it compares state_before (= state_after from step 0) vs last_review_state.
            # Since step 0 just set the review state to state_after of step 0,
            # and step 1's state_before == state_after of step 0, the magnitude is 0.
            # The auto-merge at step 1 will change state to 50.
            state_before_1 = deepcopy(board.read_state())
            step1 = asyncio.run(_run_flat_step(
                scenario, board, 1, 60, state_before_1,
                trajectory_id=0, agent_semaphore=semaphore, max_steps=max_steps,
            ))
            # Step 1 auto-merges (no review) -- state now has value=50
            assert step1.resolution is None, "Step 1 should be auto-merged"

            # Step 2: state_before has value=50, last_review_state has value=10
            # delta for value: abs(50-10)/max(10,1) = 4.0
            # delta for other: abs(5-5)/max(5,1) = 0.0
            # mean = 2.0, which is > 0.1, so adaptive review triggers
            state_before_2 = deepcopy(board.read_state())
            step2 = asyncio.run(_run_flat_step(
                scenario, board, 2, 60, state_before_2,
                trajectory_id=0, agent_semaphore=semaphore, max_steps=max_steps,
            ))
            assert step2.resolution is not None, "Step 2 should trigger adaptive review"

        finally:
            loop_module._invoke_with_retry_return = original


def test_adaptive_review_does_not_trigger_below_threshold():
    """With review_interval=5 and review_threshold=10.0 (very high),
    small state changes should NOT trigger adaptive review."""
    from minimal_agora.loop import _run_flat_step
    from minimal_agora.scenario import setup_workspace

    scenario = Scenario(
        name="test", mode=SimMode.COUNTERFACTUAL,
        initial_state={"value": 10.0},
        step_budget=10,
        review_interval=5,
        review_threshold=10.0,
        agents=[
            AgentConfig(role=AgentRole.ACTOR, name="actor_a", perspective="test"),
            AgentConfig(role=AgentRole.RESOLVER, name="resolver_a", perspective="test"),
        ],
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = setup_workspace(scenario, Path(tmpdir), trajectory_id=0)
        board = Board(workspace)
        semaphore = asyncio.Semaphore(8)

        import minimal_agora.loop as loop_module

        def _write_mock_proposal(agent, workspace, step_num):
            proposal = Proposal(
                agent=agent.name, role=AgentRole.ACTOR,
                proposed_changes={"value": 10.5},  # tiny change
                reasoning="test",
            )
            path = workspace / "proposals" / f"step_{step_num:03d}_{agent.name}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                f.write(proposal.model_dump_json(indent=2))

        async def mock_invoke(agent, workspace, step_num, prompt, timeout, max_retries=1, temperature=None):
            if agent.role == AgentRole.ACTOR:
                _write_mock_proposal(agent, workspace, step_num)

        original = loop_module._invoke_with_retry_return
        loop_module._invoke_with_retry_return = mock_invoke

        try:
            max_steps = 10

            # Step 0: review step
            state_before_0 = deepcopy(board.read_state())
            step0 = asyncio.run(_run_flat_step(
                scenario, board, 0, 60, state_before_0,
                trajectory_id=0, agent_semaphore=semaphore, max_steps=max_steps,
            ))
            assert step0.resolution is not None

            # Step 1: auto-merge, small change applied
            state_before_1 = deepcopy(board.read_state())
            step1 = asyncio.run(_run_flat_step(
                scenario, board, 1, 60, state_before_1,
                trajectory_id=0, agent_semaphore=semaphore, max_steps=max_steps,
            ))
            assert step1.resolution is None, "Step 1 should NOT trigger adaptive review"

            # Step 2: delta is still small, should not trigger
            state_before_2 = deepcopy(board.read_state())
            step2 = asyncio.run(_run_flat_step(
                scenario, board, 2, 60, state_before_2,
                trajectory_id=0, agent_semaphore=semaphore, max_steps=max_steps,
            ))
            assert step2.resolution is None, "Step 2 should NOT trigger adaptive review"

        finally:
            loop_module._invoke_with_retry_return = original


def test_adaptive_review_disabled_when_threshold_none():
    """When review_threshold is None, adaptive review should not affect behavior."""
    from minimal_agora.loop import _run_flat_step
    from minimal_agora.scenario import setup_workspace

    scenario = Scenario(
        name="test", mode=SimMode.COUNTERFACTUAL,
        initial_state={"value": 10.0},
        step_budget=10,
        review_interval=5,
        review_threshold=None,  # disabled
        agents=[
            AgentConfig(role=AgentRole.ACTOR, name="actor_a", perspective="test"),
            AgentConfig(role=AgentRole.RESOLVER, name="resolver_a", perspective="test"),
        ],
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = setup_workspace(scenario, Path(tmpdir), trajectory_id=0)
        board = Board(workspace)
        semaphore = asyncio.Semaphore(8)

        import minimal_agora.loop as loop_module

        def _write_mock_proposal(agent, workspace, step_num):
            proposal = Proposal(
                agent=agent.name, role=AgentRole.ACTOR,
                proposed_changes={"value": 9999.0},  # huge change
                reasoning="test",
            )
            path = workspace / "proposals" / f"step_{step_num:03d}_{agent.name}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                f.write(proposal.model_dump_json(indent=2))

        async def mock_invoke(agent, workspace, step_num, prompt, timeout, max_retries=1, temperature=None):
            if agent.role == AgentRole.ACTOR:
                _write_mock_proposal(agent, workspace, step_num)

        original = loop_module._invoke_with_retry_return
        loop_module._invoke_with_retry_return = mock_invoke

        try:
            max_steps = 10

            state_before_0 = deepcopy(board.read_state())
            step0 = asyncio.run(_run_flat_step(
                scenario, board, 0, 60, state_before_0,
                trajectory_id=0, agent_semaphore=semaphore, max_steps=max_steps,
            ))
            assert step0.resolution is not None

            # Step 1 should NOT review even with huge state change, because threshold is None
            state_before_1 = deepcopy(board.read_state())
            step1 = asyncio.run(_run_flat_step(
                scenario, board, 1, 60, state_before_1,
                trajectory_id=0, agent_semaphore=semaphore, max_steps=max_steps,
            ))
            assert step1.resolution is None, "Adaptive review should be disabled when threshold is None"

        finally:
            loop_module._invoke_with_retry_return = original
