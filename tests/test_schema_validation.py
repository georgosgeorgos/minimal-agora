from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from minimal_agora.models import Resolution
from minimal_agora.schema import infer_schema, validate_state_delta


class TestInferSchema:
    def test_flat_state(self):
        state = {"population": 100, "climate": "temperate", "alive": True}
        schema = infer_schema(state)
        assert schema["population"]["type"] == "int"
        assert schema["climate"]["type"] == "str"
        assert schema["alive"]["type"] == "bool"

    def test_nested_state(self):
        state = {
            "planet": {"climate": "warm", "biodiversity": 0.5},
            "life": {"complexity": 1.0, "intelligence": False},
        }
        schema = infer_schema(state)
        assert "planet.climate" in schema
        assert schema["planet.climate"]["type"] == "str"
        assert schema["planet.biodiversity"]["type"] == "float"
        assert schema["life.complexity"]["type"] == "float"
        assert schema["life.intelligence"]["type"] == "bool"

    def test_nullable_field(self):
        state = {"name": "earth", "notes": None}
        schema = infer_schema(state)
        assert schema["name"]["nullable"] is False
        assert schema["notes"]["nullable"] is True

    def test_list_and_dict_types(self):
        state = {"tags": ["a", "b"], "meta": {"x": 1}}
        schema = infer_schema(state)
        assert schema["tags"]["type"] == "list"
        assert schema["meta.x"]["type"] == "int"

    def test_deeply_nested(self):
        state = {"a": {"b": {"c": 42}}}
        schema = infer_schema(state)
        assert "a.b.c" in schema
        assert schema["a.b.c"]["type"] == "int"


class TestValidateStateDelta:
    @pytest.fixture()
    def schema(self):
        return infer_schema({
            "planet": {"climate": "warm", "biodiversity": 0.5},
            "life": {"complexity": 1.0, "intelligence": False},
            "population": 100,
        })

    def test_valid_delta(self, schema):
        delta = {"planet": {"climate": "cold", "biodiversity": 0.8}}
        errors = validate_state_delta(delta, schema)
        assert errors == []

    def test_wrong_type(self, schema):
        delta = {"population": "lots"}
        errors = validate_state_delta(delta, schema)
        assert len(errors) == 1
        assert "expected int, got str" in errors[0]

    def test_none_for_non_none_field(self, schema):
        delta = {"population": None}
        errors = validate_state_delta(delta, schema)
        assert len(errors) == 1
        assert "got None" in errors[0]

    def test_new_field_warns(self, schema):
        delta = {"new_field": "surprise"}
        errors = validate_state_delta(delta, schema)
        assert len(errors) == 1
        assert "not in original state" in errors[0]

    def test_int_to_float_compatible(self, schema):
        delta = {"life": {"complexity": 2}}
        errors = validate_state_delta(delta, schema)
        assert errors == []

    def test_float_to_str_incompatible(self, schema):
        delta = {"planet": {"biodiversity": "high"}}
        errors = validate_state_delta(delta, schema)
        assert len(errors) == 1
        assert "expected float, got str" in errors[0]

    def test_bool_type_check(self, schema):
        delta = {"life": {"intelligence": "yes"}}
        errors = validate_state_delta(delta, schema)
        assert len(errors) == 1
        assert "expected bool, got str" in errors[0]

    def test_multiple_errors(self, schema):
        delta = {
            "population": "many",
            "life": {"complexity": None},
            "unknown": 42,
        }
        errors = validate_state_delta(delta, schema)
        assert len(errors) == 3

    def test_empty_delta(self, schema):
        errors = validate_state_delta({}, schema)
        assert errors == []

    def test_nested_new_field(self, schema):
        delta = {"planet": {"atmosphere": "thick"}}
        errors = validate_state_delta(delta, schema)
        assert len(errors) == 1
        assert "planet.atmosphere" in errors[0]


class TestResolutionValidationWarnings:
    def test_resolution_accepts_warnings(self):
        r = Resolution(
            state_delta={"x": 1},
            narrative="test",
            validation_warnings=["Field x: expected int, got str"],
        )
        assert r.validation_warnings == ["Field x: expected int, got str"]

    def test_resolution_default_empty(self):
        r = Resolution(state_delta={}, narrative="test")
        assert r.validation_warnings == []


class TestLoopIntegration:
    def test_validation_runs_in_flat_step(self, tmp_path):
        from minimal_agora.board import Board
        from minimal_agora.models import AgentConfig, AgentRole, Scenario, SimMode

        workspace = tmp_path / "workspace"
        for d in ["board", "proposals", "critiques", "resolutions", "history"]:
            (workspace / d).mkdir(parents=True)

        initial_state = {"population": 100, "climate": "warm"}
        (workspace / "board" / "state.json").write_text(json.dumps(initial_state))
        (workspace / "board" / "narrative.md").write_text("")
        (workspace / "board" / "scenario.md").write_text("")

        scenario = Scenario(
            name="test",
            mode=SimMode.COUNTERFACTUAL,
            initial_state=initial_state,
            agents=[
                AgentConfig(role=AgentRole.ACTOR, name="actor1", perspective="test"),
                AgentConfig(role=AgentRole.RESOLVER, name="judge1", perspective="test"),
            ],
        )

        bad_resolution = Resolution(
            state_delta={"population": "many"},
            narrative="Population changed",
        )

        schema = infer_schema(initial_state)

        with (
            patch("minimal_agora.loop._invoke_and_collect", new_callable=AsyncMock) as mock_invoke,
            patch("minimal_agora.loop.parse_proposal_from_text") as mock_parse_prop,
            patch("minimal_agora.loop.parse_resolution_from_text") as mock_parse_res,
        ):
            from minimal_agora.models import Proposal
            from minimal_agora.providers.protocol import AgentInvocationResult

            mock_invoke.return_value = AgentInvocationResult(
                output="output", input_tokens=10, output_tokens=5,
            )
            mock_parse_prop.return_value = Proposal(
                agent="actor1",
                role=AgentRole.ACTOR,
                proposed_changes={"population": "many"},
                reasoning="test",
            )
            mock_parse_res.return_value = bad_resolution

            from minimal_agora.loop import _run_flat_step

            board = Board(workspace)
            loop = asyncio.new_event_loop()
            try:
                step = loop.run_until_complete(
                    _run_flat_step(scenario, board, 0, 30, initial_state, state_schema=schema)
                )
            finally:
                loop.close()

        assert step.resolution is not None
        assert len(step.resolution.validation_warnings) == 1
        assert "expected int, got str" in step.resolution.validation_warnings[0]
        assert step.state_after["population"] == "many"
