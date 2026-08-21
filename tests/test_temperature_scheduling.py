"""Tests for agent temperature scheduling (issue #44)."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from minimal_agora.loop import _compute_temperature
from minimal_agora.models import AgentConfig, AgentRole, Scenario, SimMode
from minimal_agora.providers.mock import MockProvider


def _make_scenario(**overrides) -> Scenario:
    defaults = {
        "name": "test-temp",
        "mode": SimMode.COUNTERFACTUAL,
        "initial_state": {"x": 1},
    }
    defaults.update(overrides)
    return Scenario(**defaults)


class TestComputeTemperatureConstant:
    def test_start_equals_end_returns_constant(self) -> None:
        scenario = _make_scenario(temperature_start=0.7, temperature_end=0.7)
        assert _compute_temperature(scenario, 0, 10) == 0.7
        assert _compute_temperature(scenario, 5, 10) == 0.7
        assert _compute_temperature(scenario, 9, 10) == 0.7

    def test_default_values_return_1(self) -> None:
        scenario = _make_scenario()
        assert _compute_temperature(scenario, 0, 10) == 1.0
        assert _compute_temperature(scenario, 9, 10) == 1.0


class TestComputeTemperatureDecreasing:
    def test_linear_interpolation(self) -> None:
        scenario = _make_scenario(temperature_start=1.0, temperature_end=0.3)
        # step 0 of 10: progress = 0/9 = 0.0 -> 1.0
        assert _compute_temperature(scenario, 0, 10) == pytest.approx(1.0)
        # step 9 of 10: progress = 9/9 = 1.0 -> 0.3
        assert _compute_temperature(scenario, 9, 10) == pytest.approx(0.3)
        # step 4 of 10: progress = 4/9 -> 1.0 + (0.3 - 1.0) * 4/9
        expected_mid = 1.0 + (0.3 - 1.0) * (4 / 9)
        assert _compute_temperature(scenario, 4, 10) == pytest.approx(expected_mid)

    def test_two_steps(self) -> None:
        scenario = _make_scenario(temperature_start=1.0, temperature_end=0.0)
        assert _compute_temperature(scenario, 0, 2) == pytest.approx(1.0)
        assert _compute_temperature(scenario, 1, 2) == pytest.approx(0.0)


class TestComputeTemperatureIncreasing:
    def test_low_to_high(self) -> None:
        scenario = _make_scenario(temperature_start=0.2, temperature_end=1.5)
        assert _compute_temperature(scenario, 0, 10) == pytest.approx(0.2)
        assert _compute_temperature(scenario, 9, 10) == pytest.approx(1.5)


class TestComputeTemperatureEdgeCases:
    def test_single_step(self) -> None:
        scenario = _make_scenario(temperature_start=1.0, temperature_end=0.3)
        # max_steps=1 -> max(0, 1) = 1 in denominator, progress = 0/1 = 0
        result = _compute_temperature(scenario, 0, 1)
        assert result == pytest.approx(1.0)

    def test_zero_max_steps(self) -> None:
        scenario = _make_scenario(temperature_start=1.0, temperature_end=0.5)
        # max(0-1, 1) = 1, so progress = 0/1 = 0
        result = _compute_temperature(scenario, 0, 0)
        assert result == pytest.approx(1.0)


class TestScenarioTemperatureDefaults:
    def test_defaults_to_1(self) -> None:
        scenario = _make_scenario()
        assert scenario.temperature_start == 1.0
        assert scenario.temperature_end == 1.0

    def test_custom_values(self) -> None:
        scenario = _make_scenario(temperature_start=0.8, temperature_end=0.2)
        assert scenario.temperature_start == 0.8
        assert scenario.temperature_end == 0.2

    def test_validation_rejects_negative(self) -> None:
        with pytest.raises(ValueError):
            _make_scenario(temperature_start=-0.1)

    def test_validation_rejects_above_2(self) -> None:
        with pytest.raises(ValueError):
            _make_scenario(temperature_end=2.1)

    def test_boundary_values(self) -> None:
        scenario = _make_scenario(temperature_start=0.0, temperature_end=2.0)
        assert scenario.temperature_start == 0.0
        assert scenario.temperature_end == 2.0


class TestProviderTemperatureOverride:
    def test_mock_provider_receives_temperature(self) -> None:
        provider = MockProvider()
        with tempfile.TemporaryDirectory() as tmp:
            asyncio.run(provider.invoke("test", Path(tmp), temperature=0.42))
        assert provider.last_temperature == 0.42

    def test_mock_provider_none_by_default(self) -> None:
        provider = MockProvider()
        with tempfile.TemporaryDirectory() as tmp:
            asyncio.run(provider.invoke("test", Path(tmp)))
        assert provider.last_temperature is None

    def test_invoke_agent_forwards_temperature(self) -> None:
        from minimal_agora.agents import invoke_agent

        provider = MockProvider(responses={"actor": '{"agent":"a","role":"actor","proposed_changes":{},"reasoning":"t","confidence":0.5}'})
        agent = AgentConfig(role=AgentRole.ACTOR, name="a", perspective="test")
        with tempfile.TemporaryDirectory() as tmp:
            asyncio.run(
                invoke_agent(agent, Path(tmp), step=0, prompt="actor test", provider=provider, temperature=0.65)
            )
        assert provider.last_temperature == 0.65

    def test_invoke_agent_none_temperature_by_default(self) -> None:
        from minimal_agora.agents import invoke_agent

        provider = MockProvider()
        agent = AgentConfig(role=AgentRole.ACTOR, name="a", perspective="test")
        with tempfile.TemporaryDirectory() as tmp:
            asyncio.run(
                invoke_agent(agent, Path(tmp), step=0, prompt="test", provider=provider)
            )
        assert provider.last_temperature is None
