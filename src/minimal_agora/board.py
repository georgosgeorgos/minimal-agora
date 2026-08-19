from __future__ import annotations

import json
from pathlib import Path

from minimal_agora.logging import get_logger
from minimal_agora.models import Critique, Proposal, Resolution, Step, WildcardEvent

logger = get_logger(__name__)


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
        logger.debug("state_read", path=str(self.state_path))
        with open(self.state_path) as f:
            return json.load(f)

    def write_state(self, state: dict) -> None:
        logger.debug("state_write", path=str(self.state_path))
        with open(self.state_path, "w") as f:
            json.dump(state, f, indent=2)

    def snapshot_state(self, step: int) -> None:
        state = self.read_state()
        path = self.workspace / "history" / f"step_{step:03d}_state.json"
        logger.info("snapshot_created", step=step, path=str(path))
        with open(path, "w") as f:
            json.dump(state, f, indent=2)

    def apply_resolution(self, resolution: Resolution, step: int) -> dict:
        logger.info("resolution_applied", step=step, delta_keys=list(resolution.state_delta.keys()))
        state = self.read_state()
        _deep_merge(state, resolution.state_delta)
        self.write_state(state)
        self.snapshot_state(step + 1)
        self._append_narrative(resolution.narrative, step)
        self._step = step + 1

        return state

    def save_proposal(self, proposal: Proposal, step: int) -> Path:
        path = self.workspace / "proposals" / f"step_{step:03d}_{proposal.agent}.json"
        logger.info("proposal_saved", step=step, agent=proposal.agent)
        with open(path, "w") as f:
            f.write(proposal.model_dump_json(indent=2))
        return path

    def save_critique(self, critique: Critique, step: int) -> Path:
        path = self.workspace / "critiques" / f"step_{step:03d}_{critique.agent}.json"
        logger.info("critique_saved", step=step, agent=critique.agent)
        with open(path, "w") as f:
            f.write(critique.model_dump_json(indent=2))
        return path

    def save_resolution(self, resolution: Resolution, step: int) -> Path:
        path = self.workspace / "resolutions" / f"step_{step:03d}_resolution.json"
        logger.info("resolution_saved", step=step)
        with open(path, "w") as f:
            f.write(resolution.model_dump_json(indent=2))
        return path

    def save_step(self, step: Step) -> Path:
        path = self.workspace / "history" / f"step_{step.step_number:03d}_full.json"
        logger.info("step_saved", step=step.step_number)
        with open(path, "w") as f:
            f.write(step.model_dump_json(indent=2))
        return path

    def read_proposals(self, step: int) -> list[Proposal]:
        proposals_dir = self.workspace / "proposals"
        results = []
        for path in sorted(proposals_dir.glob(f"step_{step:03d}_*.json")):
            with open(path) as f:
                results.append(Proposal.model_validate_json(f.read()))
        logger.debug("proposals_read", step=step, count=len(results))
        return results

    def read_critiques(self, step: int) -> list[Critique]:
        critiques_dir = self.workspace / "critiques"
        results = []
        for path in sorted(critiques_dir.glob(f"step_{step:03d}_*.json")):
            with open(path) as f:
                results.append(Critique.model_validate_json(f.read()))
        logger.debug("critiques_read", step=step, count=len(results))
        return results

    def write_wildcard(self, event: WildcardEvent, step: int) -> Path:
        path = self.workspace / "board" / f"wildcard_step_{step:03d}.json"
        logger.info("wildcard_written", step=step, wildcard_name=event.name)
        with open(path, "w") as f:
            json.dump(event.model_dump(), f, indent=2)
        return path

    def clear_wildcard(self, step: int) -> None:
        path = self.workspace / "board" / f"wildcard_step_{step:03d}.json"
        if path.exists():
            logger.debug("wildcard_cleared", step=step)
            path.unlink()

    def _append_narrative(self, text: str, step: int) -> None:
        logger.debug("narrative_append", step=step)
        with open(self.narrative_path, "a") as f:
            f.write(f"\n## Step {step + 1}\n\n")
            f.write(text)
            f.write("\n")

    def list_history(self) -> list[Path]:
        entries = sorted((self.workspace / "history").glob("step_*_state.json"))
        logger.debug("history_listed", count=len(entries))
        return entries


def _deep_merge(base: dict, overlay: dict) -> None:
    for key, value in overlay.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
