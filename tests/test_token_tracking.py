"""Tests for token tracking models and aggregation logic."""
from __future__ import annotations

import tempfile
from pathlib import Path

from minimal_agora.dashboard import _collect_data
from minimal_agora.loop import _aggregate_trajectory_tokens, _build_step_token_usage
from minimal_agora.models import (
    AgentCallTokens,
    Step,
    StepTokenUsage,
    Trajectory,
    TrajectoryOutcome,
)
from minimal_agora.providers.protocol import AgentInvocationResult


class TestAgentCallTokens:
    def test_creation(self):
        t = AgentCallTokens(role="actor", input_tokens=100, output_tokens=50)
        assert t.role == "actor"
        assert t.input_tokens == 100
        assert t.output_tokens == 50

    def test_roundtrip_json(self):
        t = AgentCallTokens(role="critic", input_tokens=200, output_tokens=75)
        data = t.model_dump_json()
        t2 = AgentCallTokens.model_validate_json(data)
        assert t2.role == "critic"
        assert t2.input_tokens == 200
        assert t2.output_tokens == 75


class TestStepTokenUsage:
    def test_empty(self):
        s = StepTokenUsage()
        assert s.agent_calls == []
        assert s.total_input_tokens == 0
        assert s.total_output_tokens == 0

    def test_with_calls(self):
        calls = [
            AgentCallTokens(role="actor", input_tokens=100, output_tokens=50),
            AgentCallTokens(role="critic", input_tokens=200, output_tokens=75),
        ]
        s = StepTokenUsage(
            agent_calls=calls,
            total_input_tokens=300,
            total_output_tokens=125,
        )
        assert len(s.agent_calls) == 2
        assert s.total_input_tokens == 300

    def test_roundtrip_json(self):
        calls = [AgentCallTokens(role="judge", input_tokens=500, output_tokens=200)]
        s = StepTokenUsage(agent_calls=calls, total_input_tokens=500, total_output_tokens=200)
        data = s.model_dump_json()
        s2 = StepTokenUsage.model_validate_json(data)
        assert len(s2.agent_calls) == 1
        assert s2.agent_calls[0].role == "judge"


class TestBuildStepTokenUsage:
    def test_empty_returns_none(self):
        assert _build_step_token_usage([]) is None

    def test_aggregates_totals(self):
        calls = [
            AgentCallTokens(role="actor", input_tokens=100, output_tokens=50),
            AgentCallTokens(role="critic", input_tokens=200, output_tokens=75),
            AgentCallTokens(role="judge", input_tokens=300, output_tokens=100),
        ]
        usage = _build_step_token_usage(calls)
        assert usage is not None
        assert usage.total_input_tokens == 600
        assert usage.total_output_tokens == 225
        assert len(usage.agent_calls) == 3


class TestAggregateTrajectoryTokens:
    def test_no_token_data_returns_none(self):
        steps = [
            Step(step_number=0, state_before={}, state_after={}),
            Step(step_number=1, state_before={}, state_after={}),
        ]
        assert _aggregate_trajectory_tokens(steps) is None

    def test_aggregates_across_steps(self):
        steps = [
            Step(
                step_number=0, state_before={}, state_after={},
                token_usage=StepTokenUsage(
                    agent_calls=[
                        AgentCallTokens(role="actor", input_tokens=100, output_tokens=50),
                        AgentCallTokens(role="critic", input_tokens=200, output_tokens=75),
                    ],
                    total_input_tokens=300, total_output_tokens=125,
                ),
            ),
            Step(
                step_number=1, state_before={}, state_after={},
                token_usage=StepTokenUsage(
                    agent_calls=[
                        AgentCallTokens(role="actor", input_tokens=150, output_tokens=60),
                        AgentCallTokens(role="judge", input_tokens=400, output_tokens=200),
                    ],
                    total_input_tokens=550, total_output_tokens=260,
                ),
            ),
        ]
        result = _aggregate_trajectory_tokens(steps)
        assert result is not None
        assert result["total_input_tokens"] == 850
        assert result["total_output_tokens"] == 385
        assert result["total_tokens"] == 1235
        assert result["estimated_cost_usd"] > 0
        assert "actor" in result["per_role"]
        assert result["per_role"]["actor"]["input_tokens"] == 250
        assert result["per_role"]["actor"]["output_tokens"] == 110
        assert "critic" in result["per_role"]
        assert "judge" in result["per_role"]

    def test_mixed_steps_with_and_without_tokens(self):
        steps = [
            Step(step_number=0, state_before={}, state_after={}),
            Step(
                step_number=1, state_before={}, state_after={},
                token_usage=StepTokenUsage(
                    agent_calls=[AgentCallTokens(role="actor", input_tokens=100, output_tokens=50)],
                    total_input_tokens=100, total_output_tokens=50,
                ),
            ),
        ]
        result = _aggregate_trajectory_tokens(steps)
        assert result is not None
        assert result["total_tokens"] == 150

    def test_cost_estimate(self):
        steps = [
            Step(
                step_number=0, state_before={}, state_after={},
                token_usage=StepTokenUsage(
                    agent_calls=[AgentCallTokens(role="actor", input_tokens=1_000_000, output_tokens=1_000_000)],
                    total_input_tokens=1_000_000, total_output_tokens=1_000_000,
                ),
            ),
        ]
        result = _aggregate_trajectory_tokens(steps)
        assert result is not None
        # $3/M input + $15/M output = $18
        assert result["estimated_cost_usd"] == 18.0


class TestStepModelWithTokens:
    def test_step_without_tokens(self):
        s = Step(step_number=0, state_before={}, state_after={})
        assert s.token_usage is None

    def test_step_with_tokens(self):
        usage = StepTokenUsage(
            agent_calls=[AgentCallTokens(role="actor", input_tokens=100, output_tokens=50)],
            total_input_tokens=100, total_output_tokens=50,
        )
        s = Step(step_number=0, state_before={}, state_after={}, token_usage=usage)
        assert s.token_usage is not None
        assert s.token_usage.total_input_tokens == 100

    def test_step_roundtrip_json(self):
        usage = StepTokenUsage(
            agent_calls=[AgentCallTokens(role="judge", input_tokens=500, output_tokens=200)],
            total_input_tokens=500, total_output_tokens=200,
        )
        s = Step(step_number=3, state_before={"x": 1}, state_after={"x": 2}, token_usage=usage)
        data = s.model_dump_json()
        s2 = Step.model_validate_json(data)
        assert s2.token_usage is not None
        assert s2.token_usage.agent_calls[0].role == "judge"


class TestTrajectoryWithTokens:
    def test_trajectory_without_tokens(self):
        t = Trajectory(scenario_name="test", trajectory_id=0)
        assert t.total_tokens is None

    def test_trajectory_with_tokens(self):
        t = Trajectory(
            scenario_name="test", trajectory_id=0,
            total_tokens={"total_input_tokens": 1000, "total_output_tokens": 500, "total_tokens": 1500},
        )
        assert t.total_tokens["total_tokens"] == 1500

    def test_trajectory_roundtrip_json(self):
        t = Trajectory(
            scenario_name="test", trajectory_id=0,
            total_tokens={"total_tokens": 2000, "estimated_cost_usd": 0.05},
            outcome=TrajectoryOutcome(classification="done", final_step=5, final_state={}),
        )
        data = t.model_dump_json()
        t2 = Trajectory.model_validate_json(data)
        assert t2.total_tokens is not None
        assert t2.total_tokens["total_tokens"] == 2000


class TestAgentInvocationResultTokens:
    def test_result_with_tokens(self):
        r = AgentInvocationResult(
            output="hello", tokens_used=150, model="test",
            input_tokens=100, output_tokens=50,
        )
        assert r.input_tokens == 100
        assert r.output_tokens == 50

    def test_result_without_tokens(self):
        r = AgentInvocationResult(output="hello")
        assert r.input_tokens is None
        assert r.output_tokens is None


class TestDashboardTokenData:
    def _make_trajectory_with_tokens(
        self, tid: int, outcome: str, steps_data: list[dict], token_data: list[StepTokenUsage | None],
    ) -> Trajectory:
        steps = []
        for i, state in enumerate(steps_data):
            tu = token_data[i] if i < len(token_data) else None
            steps.append(Step(
                step_number=i,
                state_before=steps_data[i - 1] if i > 0 else {},
                state_after=state,
                token_usage=tu,
            ))
        total = _aggregate_trajectory_tokens(steps)
        return Trajectory(
            scenario_name="test", trajectory_id=tid, steps=steps,
            outcome=TrajectoryOutcome(classification=outcome, final_step=len(steps) - 1, final_state=steps_data[-1]),
            total_tokens=total,
        )

    def _write_trajectories(self, tmpdir: Path, trajectories: list[Trajectory]):
        for t in trajectories:
            tdir = tmpdir / f"trajectory_{t.trajectory_id:03d}"
            tdir.mkdir(parents=True)
            with open(tdir / "trajectory.json", "w") as f:
                f.write(t.model_dump_json(indent=2))

    def test_collect_data_includes_token_fields(self):
        usage = StepTokenUsage(
            agent_calls=[
                AgentCallTokens(role="actor", input_tokens=100, output_tokens=50),
                AgentCallTokens(role="critic", input_tokens=200, output_tokens=75),
            ],
            total_input_tokens=300, total_output_tokens=125,
        )
        t1 = self._make_trajectory_with_tokens(0, "A", [{"x": 1}], [usage])

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            self._write_trajectories(run_dir, [t1])
            data = _collect_data(run_dir, [], [], [])

        assert "token_summary" in data
        assert data["token_summary"]["total_input_tokens"] == 300
        assert data["token_summary"]["total_output_tokens"] == 125
        assert "per_role" in data["token_summary"]
        assert "actor" in data["token_summary"]["per_role"]
        assert "token_timeline" in data
        assert len(data["token_timeline"]) == 1

    def test_collect_data_no_tokens(self):
        steps = [Step(step_number=0, state_before={}, state_after={"x": 1})]
        t1 = Trajectory(
            scenario_name="test", trajectory_id=0, steps=steps,
            outcome=TrajectoryOutcome(classification="A", final_step=0, final_state={"x": 1}),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            self._write_trajectories(run_dir, [t1])
            data = _collect_data(run_dir, [], [], [])

        assert data["token_summary"]["total_input_tokens"] == 0
        assert data["token_timeline"] == []

    def test_token_timeline_per_step(self):
        usage0 = StepTokenUsage(
            agent_calls=[AgentCallTokens(role="actor", input_tokens=100, output_tokens=50)],
            total_input_tokens=100, total_output_tokens=50,
        )
        usage1 = StepTokenUsage(
            agent_calls=[AgentCallTokens(role="actor", input_tokens=200, output_tokens=100)],
            total_input_tokens=200, total_output_tokens=100,
        )
        t1 = self._make_trajectory_with_tokens(0, "A", [{"x": 1}, {"x": 2}], [usage0, usage1])

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            self._write_trajectories(run_dir, [t1])
            data = _collect_data(run_dir, [], [], [])

        tl = data["token_timeline"]
        assert len(tl) == 2
        assert tl[0]["step"] == 0
        assert tl[0]["total_tokens"] == 150
        assert tl[1]["step"] == 1
        assert tl[1]["total_tokens"] == 300
