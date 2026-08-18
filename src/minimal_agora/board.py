from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from minimal_agora.models import (
    ConditionOperator,
    Critique,
    Proposal,
    Resolution,
    Step,
    TriggerCondition,
    WildcardEvent,
)

logger = logging.getLogger(__name__)


class Board:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.board_dir = workspace / "board"
        self._step = 0

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
        with open(self.state_path) as f:
            return json.load(f)

    def write_state(self, state: dict) -> None:
        with open(self.state_path, "w") as f:
            json.dump(state, f, indent=2)

    def snapshot_state(self, step: int) -> None:
        state = self.read_state()
        path = self.workspace / "history" / f"step_{step:03d}_state.json"
        with open(path, "w") as f:
            json.dump(state, f, indent=2)

    def apply_resolution(self, resolution: Resolution, step: int) -> dict:
        state = self.read_state()
        _deep_merge(state, resolution.state_delta)
        self.write_state(state)
        self.snapshot_state(step + 1)
        self._append_narrative(resolution.narrative, step)
        self._step = step + 1

        return state

    def save_proposal(self, proposal: Proposal, step: int) -> Path:
        path = self.workspace / "proposals" / f"step_{step:03d}_{proposal.agent}.json"
        with open(path, "w") as f:
            f.write(proposal.model_dump_json(indent=2))
        return path

    def save_critique(self, critique: Critique, step: int) -> Path:
        path = self.workspace / "critiques" / f"step_{step:03d}_{critique.agent}.json"
        with open(path, "w") as f:
            f.write(critique.model_dump_json(indent=2))
        return path

    def save_resolution(self, resolution: Resolution, step: int) -> Path:
        path = self.workspace / "resolutions" / f"step_{step:03d}_resolution.json"
        with open(path, "w") as f:
            f.write(resolution.model_dump_json(indent=2))
        return path

    def save_step(self, step: Step) -> Path:
        path = self.workspace / "history" / f"step_{step.step_number:03d}_full.json"
        with open(path, "w") as f:
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
        with open(path, "w") as f:
            json.dump(event.model_dump(), f, indent=2)
        return path

    def clear_wildcard(self, step: int) -> None:
        path = self.workspace / "board" / f"wildcard_step_{step:03d}.json"
        if path.exists():
            path.unlink()

    def _append_narrative(self, text: str, step: int) -> None:
        with open(self.narrative_path, "a") as f:
            f.write(f"\n## Step {step + 1}\n\n")
            f.write(text)
            f.write("\n")

    def list_history(self) -> list[Path]:
        return sorted((self.workspace / "history").glob("step_*_state.json"))


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
