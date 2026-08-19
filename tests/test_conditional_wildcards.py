import random

import pytest

from minimal_agora.board import evaluate_trigger_conditions, evaluate_wildcard_mode
from minimal_agora.loop import _roll_wildcard
from minimal_agora.models import (
    ConditionOperator,
    TriggerCondition,
    WildcardEvent,
    WildcardMode,
)


def test_condition_operator_values():
    assert ConditionOperator.GT == "gt"
    assert ConditionOperator.LT == "lt"
    assert ConditionOperator.EQ == "eq"
    assert ConditionOperator.GTE == "gte"
    assert ConditionOperator.LTE == "lte"


def test_trigger_condition_model():
    cond = TriggerCondition(field="population", operator=ConditionOperator.GT, threshold=1000.0)
    assert cond.field == "population"
    assert cond.operator == ConditionOperator.GT
    assert cond.threshold == 1000.0


def test_trigger_condition_from_dict():
    cond = TriggerCondition.model_validate(
        {"field": "economy.gdp", "operator": "lt", "threshold": 50.0}
    )
    assert cond.operator == ConditionOperator.LT
    assert cond.field == "economy.gdp"


def test_wildcard_event_with_conditions():
    event = WildcardEvent(
        name="pandemic",
        probability=0.05,
        trigger_conditions=[
            TriggerCondition(field="population", operator=ConditionOperator.GT, threshold=1000000),
        ],
    )
    assert len(event.trigger_conditions) == 1
    assert event.trigger_conditions[0].field == "population"


def test_wildcard_event_without_conditions_backward_compatible():
    event = WildcardEvent(name="test", probability=0.5)
    assert event.trigger_conditions == []


def test_wildcard_event_roundtrip():
    event = WildcardEvent(
        name="test",
        probability=0.3,
        trigger_conditions=[
            TriggerCondition(field="x.y", operator=ConditionOperator.GTE, threshold=10.0),
        ],
    )
    data = event.model_dump_json()
    restored = WildcardEvent.model_validate_json(data)
    assert len(restored.trigger_conditions) == 1
    assert restored.trigger_conditions[0].operator == ConditionOperator.GTE


# --- evaluate_trigger_conditions ---


def test_evaluate_gt_pass():
    conds = [TriggerCondition(field="pop", operator=ConditionOperator.GT, threshold=100)]
    assert evaluate_trigger_conditions(conds, {"pop": 200}) is True


def test_evaluate_gt_fail():
    conds = [TriggerCondition(field="pop", operator=ConditionOperator.GT, threshold=100)]
    assert evaluate_trigger_conditions(conds, {"pop": 50}) is False


def test_evaluate_gt_equal_fails():
    conds = [TriggerCondition(field="pop", operator=ConditionOperator.GT, threshold=100)]
    assert evaluate_trigger_conditions(conds, {"pop": 100}) is False


def test_evaluate_lt_pass():
    conds = [TriggerCondition(field="temp", operator=ConditionOperator.LT, threshold=0)]
    assert evaluate_trigger_conditions(conds, {"temp": -5}) is True


def test_evaluate_lt_fail():
    conds = [TriggerCondition(field="temp", operator=ConditionOperator.LT, threshold=0)]
    assert evaluate_trigger_conditions(conds, {"temp": 10}) is False


def test_evaluate_eq_pass():
    conds = [TriggerCondition(field="level", operator=ConditionOperator.EQ, threshold=5.0)]
    assert evaluate_trigger_conditions(conds, {"level": 5}) is True


def test_evaluate_eq_fail():
    conds = [TriggerCondition(field="level", operator=ConditionOperator.EQ, threshold=5.0)]
    assert evaluate_trigger_conditions(conds, {"level": 6}) is False


def test_evaluate_gte_pass_equal():
    conds = [TriggerCondition(field="score", operator=ConditionOperator.GTE, threshold=80)]
    assert evaluate_trigger_conditions(conds, {"score": 80}) is True


def test_evaluate_gte_pass_greater():
    conds = [TriggerCondition(field="score", operator=ConditionOperator.GTE, threshold=80)]
    assert evaluate_trigger_conditions(conds, {"score": 90}) is True


def test_evaluate_gte_fail():
    conds = [TriggerCondition(field="score", operator=ConditionOperator.GTE, threshold=80)]
    assert evaluate_trigger_conditions(conds, {"score": 79}) is False


def test_evaluate_lte_pass_equal():
    conds = [TriggerCondition(field="risk", operator=ConditionOperator.LTE, threshold=10)]
    assert evaluate_trigger_conditions(conds, {"risk": 10}) is True


def test_evaluate_lte_pass_less():
    conds = [TriggerCondition(field="risk", operator=ConditionOperator.LTE, threshold=10)]
    assert evaluate_trigger_conditions(conds, {"risk": 5}) is True


def test_evaluate_lte_fail():
    conds = [TriggerCondition(field="risk", operator=ConditionOperator.LTE, threshold=10)]
    assert evaluate_trigger_conditions(conds, {"risk": 15}) is False


def test_evaluate_nested_field():
    conds = [TriggerCondition(field="economy.debt_ratio", operator=ConditionOperator.GT, threshold=2.0)]
    assert evaluate_trigger_conditions(conds, {"economy": {"debt_ratio": 3.0}}) is True
    assert evaluate_trigger_conditions(conds, {"economy": {"debt_ratio": 1.5}}) is False


def test_evaluate_missing_field_fails():
    conds = [TriggerCondition(field="nonexistent", operator=ConditionOperator.GT, threshold=0)]
    assert evaluate_trigger_conditions(conds, {"other": 5}) is False


def test_evaluate_non_numeric_field_fails():
    conds = [TriggerCondition(field="status", operator=ConditionOperator.GT, threshold=0)]
    assert evaluate_trigger_conditions(conds, {"status": "active"}) is False


def test_evaluate_empty_conditions_passes():
    assert evaluate_trigger_conditions([], {"anything": 42}) is True


def test_evaluate_multiple_conditions_all_must_pass():
    conds = [
        TriggerCondition(field="pop", operator=ConditionOperator.GT, threshold=100),
        TriggerCondition(field="density", operator=ConditionOperator.GT, threshold=50),
    ]
    assert evaluate_trigger_conditions(conds, {"pop": 200, "density": 80}) is True
    assert evaluate_trigger_conditions(conds, {"pop": 200, "density": 30}) is False
    assert evaluate_trigger_conditions(conds, {"pop": 50, "density": 80}) is False


# --- _roll_wildcard with conditions ---


def test_roll_wildcard_skips_when_conditions_not_met():
    events = [
        WildcardEvent(
            name="conditional",
            probability=10.0,
            mode=WildcardMode.CONDITIONAL,
            trigger_conditions=[
                TriggerCondition(field="pop", operator=ConditionOperator.GT, threshold=1000),
            ],
        ),
    ]
    random.seed(42)
    result = _roll_wildcard(events, max_steps=1, state={"pop": 500})
    assert result is None


def test_roll_wildcard_fires_when_conditions_met():
    events = [
        WildcardEvent(
            name="conditional",
            probability=10.0,
            mode=WildcardMode.CONDITIONAL,
            trigger_conditions=[
                TriggerCondition(field="pop", operator=ConditionOperator.GT, threshold=1000),
            ],
        ),
    ]
    random.seed(42)
    result = _roll_wildcard(events, max_steps=1, state={"pop": 2000})
    assert result is not None
    assert result.name == "conditional"


def test_roll_wildcard_no_conditions_backward_compatible():
    events = [WildcardEvent(name="plain", probability=10.0)]
    random.seed(42)
    result = _roll_wildcard(events, max_steps=10)
    assert result is not None
    assert result.name == "plain"


def test_roll_wildcard_no_state_skips_conditional():
    events = [
        WildcardEvent(
            name="needs_state",
            probability=10.0,
            mode=WildcardMode.CONDITIONAL,
            trigger_conditions=[
                TriggerCondition(field="x", operator=ConditionOperator.GT, threshold=0),
            ],
        ),
    ]
    result = _roll_wildcard(events, max_steps=1, state=None)
    assert result is None


def test_roll_wildcard_mixed_conditional_and_plain():
    events = [
        WildcardEvent(
            name="conditional_skip",
            probability=10.0,
            mode=WildcardMode.CONDITIONAL,
            trigger_conditions=[
                TriggerCondition(field="pop", operator=ConditionOperator.GT, threshold=9999),
            ],
        ),
        WildcardEvent(name="plain", probability=10.0),
    ]
    random.seed(42)
    result = _roll_wildcard(events, max_steps=1, state={"pop": 100})
    assert result is not None
    assert result.name == "plain"


def test_pandemic_scenario_loads_with_modes():
    from pathlib import Path

    from minimal_agora.scenario import load_scenario

    examples = Path(__file__).parent.parent / "scenarios" / "examples"
    scenario = load_scenario(examples / "pandemic.yaml")
    assert len(scenario.wildcards) == 3

    mutation = next(w for w in scenario.wildcards if w.name == "mutation")
    assert mutation.mode == WildcardMode.RANDOM
    assert len(mutation.trigger_conditions) == 0

    spreader = next(w for w in scenario.wildcards if w.name == "super_spreader_event")
    assert spreader.mode == WildcardMode.CONDITIONAL
    assert len(spreader.trigger_conditions) == 1
    assert spreader.trigger_conditions[0].field == "disease.transmissibility"
    assert spreader.trigger_conditions[0].operator == ConditionOperator.GTE

    misinfo = next(w for w in scenario.wildcards if w.name == "misinformation_wave")
    assert misinfo.mode == WildcardMode.HYBRID
    assert misinfo.probability_boost == 3.0
    assert len(misinfo.trigger_conditions) == 1
    assert misinfo.trigger_conditions[0].operator == ConditionOperator.LT


# --- WildcardMode enum and defaults ---


def test_wildcard_mode_values():
    assert WildcardMode.RANDOM == "random"
    assert WildcardMode.CONDITIONAL == "conditional"
    assert WildcardMode.HYBRID == "hybrid"


def test_wildcard_default_mode_is_random():
    event = WildcardEvent(name="test", probability=0.5)
    assert event.mode == WildcardMode.RANDOM


def test_wildcard_default_probability_boost():
    event = WildcardEvent(name="test", probability=0.5)
    assert event.probability_boost == 2.0


def test_wildcard_conditional_mode_requires_conditions():
    with pytest.raises(ValueError, match="CONDITIONAL mode requires at least one trigger_condition"):
        WildcardEvent(name="bad", probability=0.5, mode=WildcardMode.CONDITIONAL)


def test_wildcard_conditional_mode_with_conditions_ok():
    event = WildcardEvent(
        name="ok",
        probability=0.5,
        mode=WildcardMode.CONDITIONAL,
        trigger_conditions=[
            TriggerCondition(field="x", operator=ConditionOperator.GT, threshold=0),
        ],
    )
    assert event.mode == WildcardMode.CONDITIONAL


def test_wildcard_hybrid_mode_without_conditions_ok():
    event = WildcardEvent(name="hybrid_no_conds", probability=0.5, mode=WildcardMode.HYBRID)
    assert event.mode == WildcardMode.HYBRID


def test_wildcard_mode_roundtrip():
    event = WildcardEvent(
        name="test",
        probability=0.3,
        mode=WildcardMode.HYBRID,
        probability_boost=3.5,
        trigger_conditions=[
            TriggerCondition(field="x", operator=ConditionOperator.GT, threshold=10),
        ],
    )
    data = event.model_dump_json()
    restored = WildcardEvent.model_validate_json(data)
    assert restored.mode == WildcardMode.HYBRID
    assert restored.probability_boost == 3.5


# --- evaluate_wildcard_mode ---


def test_evaluate_random_mode_ignores_conditions():
    event = WildcardEvent(
        name="random_with_conds",
        probability=0.5,
        mode=WildcardMode.RANDOM,
        trigger_conditions=[
            TriggerCondition(field="pop", operator=ConditionOperator.GT, threshold=9999),
        ],
    )
    result = evaluate_wildcard_mode(event, 0.1, {"pop": 1})
    assert result == 0.1


def test_evaluate_conditional_mode_returns_none_when_not_met():
    event = WildcardEvent(
        name="cond",
        probability=0.5,
        mode=WildcardMode.CONDITIONAL,
        trigger_conditions=[
            TriggerCondition(field="pop", operator=ConditionOperator.GT, threshold=1000),
        ],
    )
    result = evaluate_wildcard_mode(event, 0.1, {"pop": 500})
    assert result is None


def test_evaluate_conditional_mode_returns_prob_when_met():
    event = WildcardEvent(
        name="cond",
        probability=0.5,
        mode=WildcardMode.CONDITIONAL,
        trigger_conditions=[
            TriggerCondition(field="pop", operator=ConditionOperator.GT, threshold=1000),
        ],
    )
    result = evaluate_wildcard_mode(event, 0.1, {"pop": 2000})
    assert result == 0.1


def test_evaluate_conditional_mode_no_state():
    event = WildcardEvent(
        name="cond",
        probability=0.5,
        mode=WildcardMode.CONDITIONAL,
        trigger_conditions=[
            TriggerCondition(field="x", operator=ConditionOperator.GT, threshold=0),
        ],
    )
    result = evaluate_wildcard_mode(event, 0.1, None)
    assert result is None


def test_evaluate_hybrid_mode_base_when_conditions_not_met():
    event = WildcardEvent(
        name="hybrid",
        probability=0.5,
        mode=WildcardMode.HYBRID,
        probability_boost=3.0,
        trigger_conditions=[
            TriggerCondition(field="debt", operator=ConditionOperator.GT, threshold=100),
        ],
    )
    result = evaluate_wildcard_mode(event, 0.1, {"debt": 50})
    assert result == 0.1


def test_evaluate_hybrid_mode_boosted_when_conditions_met():
    event = WildcardEvent(
        name="hybrid",
        probability=0.5,
        mode=WildcardMode.HYBRID,
        probability_boost=3.0,
        trigger_conditions=[
            TriggerCondition(field="debt", operator=ConditionOperator.GT, threshold=100),
        ],
    )
    result = evaluate_wildcard_mode(event, 0.1, {"debt": 200})
    assert result == pytest.approx(0.3)


def test_evaluate_hybrid_mode_boost_capped_at_one():
    event = WildcardEvent(
        name="hybrid",
        probability=0.9,
        mode=WildcardMode.HYBRID,
        probability_boost=5.0,
        trigger_conditions=[
            TriggerCondition(field="x", operator=ConditionOperator.GT, threshold=0),
        ],
    )
    result = evaluate_wildcard_mode(event, 0.9, {"x": 10})
    assert result == 1.0


def test_evaluate_hybrid_mode_no_conditions_always_base():
    event = WildcardEvent(
        name="hybrid_no_conds",
        probability=0.5,
        mode=WildcardMode.HYBRID,
    )
    result = evaluate_wildcard_mode(event, 0.1, {"anything": 42})
    assert result == 0.1


# --- _roll_wildcard with modes ---


def test_roll_wildcard_random_mode_fires_regardless_of_state():
    events = [
        WildcardEvent(
            name="random_with_conds",
            probability=10.0,
            mode=WildcardMode.RANDOM,
            trigger_conditions=[
                TriggerCondition(field="pop", operator=ConditionOperator.GT, threshold=9999),
            ],
        ),
    ]
    random.seed(42)
    result = _roll_wildcard(events, max_steps=1, state={"pop": 1})
    assert result is not None
    assert result.name == "random_with_conds"


def test_roll_wildcard_hybrid_mode_fires_at_base():
    events = [
        WildcardEvent(
            name="hybrid",
            probability=10.0,
            mode=WildcardMode.HYBRID,
            probability_boost=2.0,
            trigger_conditions=[
                TriggerCondition(field="x", operator=ConditionOperator.GT, threshold=9999),
            ],
        ),
    ]
    random.seed(42)
    result = _roll_wildcard(events, max_steps=1, state={"x": 0})
    assert result is not None
    assert result.name == "hybrid"
