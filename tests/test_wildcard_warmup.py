import random

from minimal_agora.loop import _roll_wildcard
from minimal_agora.models import WildcardEvent


def _make_events():
    return [WildcardEvent(name="shock", probability=10.0)]


def test_warmup_suppresses_wildcard_during_warmup_period():
    events = _make_events()
    random.seed(42)
    result = _roll_wildcard(events, max_steps=100, state={}, step_num=0, warmup=0.05)
    assert result is None

    result = _roll_wildcard(events, max_steps=100, state={}, step_num=4, warmup=0.05)
    assert result is None


def test_warmup_allows_wildcard_after_warmup_period():
    events = _make_events()
    random.seed(42)
    result = _roll_wildcard(events, max_steps=1, state={}, step_num=5, warmup=0.05)
    assert result is not None
    assert result.name == "shock"


def test_warmup_zero_disables_suppression():
    events = _make_events()
    random.seed(42)
    result = _roll_wildcard(events, max_steps=1, state={}, step_num=0, warmup=0.0)
    assert result is not None
    assert result.name == "shock"


def test_warmup_boundary_step_fires():
    events = _make_events()
    random.seed(42)
    boundary = int(100 * 0.05)
    assert boundary == 5
    result = _roll_wildcard(events, max_steps=1, state={}, step_num=boundary, warmup=0.05)
    assert result is not None


def test_warmup_one_before_boundary_suppressed():
    events = _make_events()
    random.seed(42)
    boundary = int(100 * 0.05)
    result = _roll_wildcard(events, max_steps=100, state={}, step_num=boundary - 1, warmup=0.05)
    assert result is None


def test_warmup_default_parameter():
    events = _make_events()
    random.seed(42)
    result = _roll_wildcard(events, max_steps=100, state={}, step_num=0)
    assert result is None

    random.seed(42)
    result = _roll_wildcard(events, max_steps=1, state={}, step_num=5)
    assert result is not None
