"""Pure policy and extrapolation helpers for adaptive step execution."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from minimal_agora.board import compute_state_delta_magnitude
from minimal_agora.models import AdaptiveStepConfig, Step


def should_reason(
    config: AdaptiveStepConfig,
    *,
    step_num: int,
    max_steps: int,
    current_state: dict[str, Any],
    last_reasoned_step: Step | None,
    wildcard_active: bool,
) -> bool:
    """Return whether a step needs the full LLM reasoning loop."""
    if step_num == 0 or step_num == max_steps - 1 or wildcard_active:
        return True
    if step_num % config.reasoning_interval == 0:
        return True
    if last_reasoned_step is None:
        return True
    if config.change_threshold is None:
        return False

    magnitude = compute_state_delta_magnitude(last_reasoned_step.state_after, current_state)
    return magnitude >= config.change_threshold


def extrapolate_numeric_state(
    current_state: dict[str, Any],
    last_reasoned_step: Step,
) -> dict[str, Any]:
    """Repeat numeric leaf deltas from the most recent reasoned step.

    Non-numeric values and fields whose shape changed during the source step are
    held constant. The input state is never mutated.
    """
    result = deepcopy(current_state)
    _apply_numeric_deltas(
        result,
        last_reasoned_step.state_before,
        last_reasoned_step.state_after,
    )
    return result


def _apply_numeric_deltas(current: dict, before: dict, after: dict) -> None:
    for key in before.keys() & after.keys() & current.keys():
        before_value = before[key]
        after_value = after[key]
        current_value = current[key]

        if all(isinstance(value, dict) for value in (before_value, after_value, current_value)):
            _apply_numeric_deltas(current_value, before_value, after_value)
            continue

        values = (before_value, after_value, current_value)
        if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values):
            current[key] = current_value + (after_value - before_value)
