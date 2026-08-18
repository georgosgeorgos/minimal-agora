import random

from minimal_agora.board import evaluate_trigger_conditions
from minimal_agora.loop import _roll_wildcard
from minimal_agora.models import (
    ConditionOperator,
    TriggerCondition,
    WildcardEvent,
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


def test_pandemic_scenario_loads_with_conditions():
    from pathlib import Path

    from minimal_agora.scenario import load_scenario

    examples = Path(__file__).parent.parent / "scenarios" / "examples"
    scenario = load_scenario(examples / "pandemic.yaml")
    assert len(scenario.wildcards) == 3

    spreader = next(w for w in scenario.wildcards if w.name == "super_spreader_event")
    assert len(spreader.trigger_conditions) == 1
    assert spreader.trigger_conditions[0].field == "disease.transmissibility"
    assert spreader.trigger_conditions[0].operator == ConditionOperator.GTE

    misinfo = next(w for w in scenario.wildcards if w.name == "misinformation_wave")
    assert len(misinfo.trigger_conditions) == 1
    assert misinfo.trigger_conditions[0].operator == ConditionOperator.LT

    mutation = next(w for w in scenario.wildcards if w.name == "mutation")
    assert len(mutation.trigger_conditions) == 0
