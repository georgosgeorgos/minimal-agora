from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO

import structlog

from minimal_agora.models import (
    ConditionOperator,
    Critique,
    Proposal,
    Resolution,
    Step,
    TriggerCondition,
    WildcardEvent,
    WildcardMode,
)

logger = structlog.stdlib.get_logger(__name__)


@contextmanager
def _atomic_write(filepath: Path) -> Iterator[IO[str]]:
    directory = filepath.parent
    fd, temppath = tempfile.mkstemp(dir=str(directory), prefix=".tmp_", suffix=filepath.suffix)
    try:
        f = os.fdopen(fd, "w", encoding="utf-8")
        with f:
            yield f
            f.flush()
            os.fsync(f.fileno())
            logger.debug("checkpoint.write", path=str(filepath))
        os.replace(temppath, str(filepath))
        logger.debug("checkpoint.atomic_rename", path=str(filepath))
    except Exception:
        try:
            os.unlink(temppath)
        except OSError:
            pass
        raise


class Board:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.board_dir = workspace / "board"
        self._step = 0
        self._last_review_state: dict | None = None

    @property
    def state_path(self) -> Path:
        return self.board_dir / "state.json"

    @property
    def narrative_path(self) -> Path:
        return self.board_dir / "narrative.md"

    @property
    def scenario_path(self) -> Path:
        return self.board_dir / "scenario.md"

    def read_state(self) -> dict:
        logger.debug("board.read_state", path=str(self.state_path))
        with open(self.state_path) as f:
            return json.load(f)

    def write_state(self, state: dict) -> None:
        logger.debug("board.write_state", path=str(self.state_path))
        with _atomic_write(self.state_path) as f:
            json.dump(state, f, indent=2)

    def snapshot_state(self, step: int) -> None:
        state = self.read_state()
        path = self.workspace / "history" / f"step_{step:03d}_state.json"
        logger.info("board.snapshot_state", step=step, path=str(path))
        with _atomic_write(path) as f:
            json.dump(state, f, indent=2)

    def apply_resolution(self, resolution: Resolution, step: int) -> dict:
        logger.info("board.apply_resolution", step=step, delta_keys=list(resolution.state_delta.keys()))
        state = self.read_state()
        expanded = _expand_dotted_keys(resolution.state_delta)
        _deep_merge(state, expanded)
        self.write_state(state)
        self.snapshot_state(step + 1)
        self._append_narrative(resolution.narrative, step)
        self._step = step + 1

        return state

    def save_proposal(self, proposal: Proposal, step: int) -> Path:
        path = self.workspace / "proposals" / f"step_{step:03d}_{proposal.agent}.json"
        with _atomic_write(path) as f:
            f.write(proposal.model_dump_json(indent=2))
        return path

    def save_critique(self, critique: Critique, step: int) -> Path:
        path = self.workspace / "critiques" / f"step_{step:03d}_{critique.agent}.json"
        with _atomic_write(path) as f:
            f.write(critique.model_dump_json(indent=2))
        return path

    def save_resolution(self, resolution: Resolution, step: int) -> Path:
        path = self.workspace / "resolutions" / f"step_{step:03d}_resolution.json"
        with _atomic_write(path) as f:
            f.write(resolution.model_dump_json(indent=2))
        return path

    def save_step(self, step: Step) -> Path:
        path = self.workspace / "history" / f"step_{step.step_number:03d}_full.json"
        with _atomic_write(path) as f:
            f.write(step.model_dump_json(indent=2))
        return path

    def read_proposals(self, step: int) -> list[Proposal]:
        proposals_dir = self.workspace / "proposals"
        results = []
        for path in sorted(proposals_dir.glob(f"step_{step:03d}_*.json")):
            with open(path) as f:
                results.append(Proposal.model_validate_json(f.read()))
        return results

    def read_critiques(self, step: int) -> list[Critique]:
        critiques_dir = self.workspace / "critiques"
        results = []
        for path in sorted(critiques_dir.glob(f"step_{step:03d}_*.json")):
            with open(path) as f:
                results.append(Critique.model_validate_json(f.read()))
        return results

    def write_wildcard(self, event: WildcardEvent, step: int) -> Path:
        path = self.workspace / "board" / f"wildcard_step_{step:03d}.json"
        logger.info("board.write_wildcard", step=step, wildcard=event.name)
        with _atomic_write(path) as f:
            json.dump(event.model_dump(), f, indent=2)
        return path

    def clear_wildcard(self, step: int) -> None:
        path = self.workspace / "board" / f"wildcard_step_{step:03d}.json"
        if path.exists():
            path.unlink()

    def _append_narrative(self, text: str, step: int) -> None:
        logger.debug("board.append_narrative", step=step, length=len(text))
        with open(self.narrative_path, "a") as f:
            f.write(f"\n## Step {step + 1}\n\n")
            f.write(text)
            f.write("\n")

    def list_history(self) -> list[Path]:
        return sorted((self.workspace / "history").glob("step_*_state.json"))

    def set_last_review_state(self, state: dict) -> None:
        """Store a copy of the state at the last review step."""
        from copy import deepcopy

        self._last_review_state = deepcopy(state)

    def get_state_delta_magnitude(self, current_state: dict) -> float | None:
        """Compute magnitude of state change since last review.

        Returns None if no previous review state has been recorded.
        """
        if self._last_review_state is None:
            return None
        return compute_state_delta_magnitude(self._last_review_state, current_state)


def _flatten_state(state: dict, prefix: str = "") -> dict[str, float]:
    """Recursively flatten nested dicts, keeping only numeric values."""
    flat: dict[str, float] = {}
    for k, v in state.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            flat.update(_flatten_state(v, key))
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            flat[key] = float(v)
    return flat


def compute_state_delta_magnitude(state_before: dict, state_after: dict) -> float:
    """Compute mean relative change across shared numeric fields.

    For each shared numeric field, computes abs(after - before) / max(abs(before), 1.0).
    Returns the mean of these relative changes, or 0.0 if no shared numeric fields exist.
    """
    flat_before = _flatten_state(state_before)
    flat_after = _flatten_state(state_after)

    shared_keys = set(flat_before.keys()) & set(flat_after.keys())
    if not shared_keys:
        return 0.0

    total = 0.0
    for key in shared_keys:
        before_val = flat_before[key]
        after_val = flat_after[key]
        total += abs(after_val - before_val) / max(abs(before_val), 1.0)

    return total / len(shared_keys)


def _expand_dotted_keys(d: dict) -> dict:
    result: dict = {}
    for key, value in d.items():
        if isinstance(value, dict):
            value = _expand_dotted_keys(value)
        if "." in key:
            parts = key.split(".")
            current = result
            for part in parts[:-1]:
                if part not in current or not isinstance(current[part], dict):
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value
        else:
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                _deep_merge(result[key], value)
            else:
                result[key] = value
    return result


def _deep_merge(base: dict, overlay: dict) -> None:
    for key, value in overlay.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _get_nested(d: dict, path: str):
    keys = path.split(".")
    current = d
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


_CONDITION_OPS = {
    ConditionOperator.GT: lambda v, t: v > t,
    ConditionOperator.LT: lambda v, t: v < t,
    ConditionOperator.EQ: lambda v, t: float(v) == t,
    ConditionOperator.GTE: lambda v, t: v >= t,
    ConditionOperator.LTE: lambda v, t: v <= t,
}


def compress_narrative(narrative: str, window: int = 20) -> str:
    _STEP_HEADER = re.compile(r"^## Step (\d+)$", re.MULTILINE)
    matches = [(m, int(m.group(1))) for m in _STEP_HEADER.finditer(narrative) if int(m.group(1)) >= 1]

    if len(matches) <= window:
        logger.debug("narrative has %d steps, within window %d — no compression", len(matches), window)
        return narrative

    logger.info("compressing narrative: %d steps, keeping %d recent", len(matches), window)

    steps: list[tuple[str, str]] = []
    for i, (match, _step_num) in enumerate(matches):
        header = match.group(0)
        body_start = match.end()
        body_end = matches[i + 1][0].start() if i + 1 < len(matches) else len(narrative)
        body = narrative[body_start:body_end].strip()
        steps.append((header, body))

    preamble = narrative[: matches[0][0].start()]

    summary_marker = "## Summary of Earlier Steps"
    existing_summary = ""
    clean_preamble = preamble
    if summary_marker in preamble:
        idx = preamble.index(summary_marker)
        existing_summary = preamble[idx + len(summary_marker) :].strip()
        clean_preamble = preamble[:idx].rstrip() + "\n\n"

    old_steps = steps[:-window]
    recent_steps = steps[-window:]

    batch_size = 10
    summary_parts: list[str] = []
    if existing_summary:
        summary_parts.append(existing_summary)

    for i in range(0, len(old_steps), batch_size):
        batch = old_steps[i : i + batch_size]
        sentences = [_extract_first_sentence(body) for _, body in batch if body]
        if sentences:
            summary_parts.append(" ".join(sentences))

    result = clean_preamble.rstrip("\n") + "\n\n"
    if summary_parts:
        result += summary_marker + "\n\n"
        result += "\n\n".join(summary_parts)
        result += "\n"

    for header, body in recent_steps:
        result += f"\n{header}\n\n{body}\n"

    return result


def _extract_first_sentence(text: str) -> str:
    dot = text.find(".")
    if dot >= 0:
        return text[: dot + 1]
    return (text[:100].rstrip() + "...") if len(text) > 100 else text


def evaluate_trigger_conditions(conditions: list[TriggerCondition], state: dict) -> bool:
    for cond in conditions:
        value = _get_nested(state, cond.field)
        if value is None or not isinstance(value, (int, float)):
            logger.debug(
                "trigger_condition field=%s not found or not numeric, condition fails",
                cond.field,
            )
            return False

        op_fn = _CONDITION_OPS[cond.operator]
        passed = op_fn(value, cond.threshold)

        logger.debug(
            "trigger_condition field=%s op=%s threshold=%s value=%s → %s",
            cond.field, cond.operator.value, cond.threshold, value,
            "passed" if passed else "failed",
        )
        if not passed:
            return False

    logger.debug("all trigger_conditions satisfied (%d conditions)", len(conditions))
    return True


def evaluate_wildcard_mode(
    event: WildcardEvent, per_step_prob: float, state: dict | None,
) -> float | None:
    mode = event.mode

    if mode == WildcardMode.RANDOM:
        logger.debug("wildcard %s mode=random, probability=%s", event.name, per_step_prob)
        return per_step_prob

    conditions_met = (
        state is not None
        and event.trigger_conditions
        and evaluate_trigger_conditions(event.trigger_conditions, state)
    )

    if mode == WildcardMode.CONDITIONAL:
        if not conditions_met:
            logger.debug("wildcard %s mode=conditional, conditions not met — skipped", event.name)
            return None
        logger.debug("wildcard %s mode=conditional, conditions met, probability=%s", event.name, per_step_prob)
        return per_step_prob

    # HYBRID: always eligible, boosted when conditions met
    if conditions_met:
        boosted = min(per_step_prob * event.probability_boost, 1.0)
        logger.debug(
            "wildcard %s mode=hybrid, conditions met, boosted probability=%s (%.1fx)",
            event.name, boosted, event.probability_boost,
        )
        return boosted

    logger.debug("wildcard %s mode=hybrid, conditions not met, probability=%s", event.name, per_step_prob)
    return per_step_prob
