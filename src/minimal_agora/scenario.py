from __future__ import annotations

import json
import shutil
from pathlib import Path

import structlog
import yaml

from minimal_agora.board import _deep_merge
from minimal_agora.models import Scenario

logger = structlog.stdlib.get_logger(__name__)


def load_scenario(path: str | Path) -> Scenario:
    """Load and validate a scenario from a YAML or JSON file."""
    path = Path(path)
    logger.info("scenario.load", path=str(path), format=path.suffix)
    with open(path) as f:
        if path.suffix in (".yaml", ".yml"):
            data = yaml.safe_load(f)
        else:
            data = json.load(f)
    scenario = Scenario.model_validate(data)
    logger.info(
        "scenario.loaded",
        name=scenario.name,
        mode=scenario.mode.value,
        n_agents=len(scenario.agents),
        n_entities=len(scenario.entities),
    )
    return scenario


def setup_workspace(scenario: Scenario, workspace: Path, trajectory_id: int = 0) -> Path:
    workspace = workspace / f"trajectory_{trajectory_id:03d}"
    logger.info("scenario.setup_workspace", trajectory_id=trajectory_id, path=str(workspace))
    workspace.mkdir(parents=True, exist_ok=True)

    board = workspace / "board"
    board.mkdir(exist_ok=True)
    (workspace / "proposals").mkdir(exist_ok=True)
    (workspace / "critiques").mkdir(exist_ok=True)
    (workspace / "resolutions").mkdir(exist_ok=True)
    (workspace / "history").mkdir(exist_ok=True)

    full_state = dict(scenario.initial_state)
    for entity in scenario.entities:
        if entity.initial_state and entity.state_prefix:
            nested = _build_nested(entity.state_prefix, entity.initial_state)
            _deep_merge(full_state, nested)

    with open(board / "state.json", "w") as f:
        json.dump(full_state, f, indent=2)

    with open(board / "scenario.md", "w") as f:
        f.write(f"# {scenario.name}\n\n")
        if scenario.description:
            f.write(f"{scenario.description}\n\n")
        if scenario.agents:
            f.write("## Agents\n\n")
            for agent in scenario.agents:
                f.write(f"### {agent.name} ({agent.role.value})\n")
                f.write(f"{agent.perspective}\n\n")
        if scenario.entities:
            f.write("## Entities\n\n")
            for entity in scenario.entities:
                f.write(f"### {entity.name} ({entity.type.value})\n")
                if entity.state_prefix:
                    f.write(f"State prefix: `{entity.state_prefix}`\n\n")
                for agent in entity.agents:
                    f.write(f"- **{agent.name}** ({agent.role.value}): {agent.perspective.strip()[:120]}...\n")
                f.write("\n")
        if scenario.rules:
            f.write("## Rules\n\n")
            f.writelines(f"- **{rule.name}**: {rule.description.strip()}\n" for rule in scenario.rules)
            f.write("\n")
        if scenario.termination:
            f.write("## Termination Conditions\n\n")
            max_steps = scenario.termination.get("max_steps", scenario.step_budget)
            f.write(f"- Max steps: {max_steps}\n")
            f.writelines(f"- {cond['field']} {_format_condition(cond)}\n" for cond in scenario.termination.get("conditions", []))
        f.write("\n")

    with open(board / "narrative.md", "w") as f:
        f.write(f"# {scenario.name} — Narrative Log\n\n")
        f.write("## Step 0 — Initial State\n\n")
        f.write(_state_summary(scenario.initial_state))
        f.write("\n")

    snapshot = workspace / "history" / "step_000_state.json"
    with open(snapshot, "w") as f:
        json.dump(scenario.initial_state, f, indent=2)

    return workspace


def teardown_workspace(workspace: Path) -> None:
    logger.info("scenario.teardown_workspace", path=str(workspace))
    if workspace.exists():
        shutil.rmtree(workspace)


def _build_nested(prefix: str, value: dict) -> dict:
    keys = prefix.split(".")
    result = value
    for key in reversed(keys):
        result = {key: result}
    return result


def _format_condition(cond: dict) -> str:
    if "equals" in cond:
        return f"== {cond['equals']}"
    if "greater_than" in cond:
        return f"> {cond['greater_than']}"
    if "less_than" in cond:
        return f"< {cond['less_than']}"
    return ""


def _state_summary(state: dict, indent: int = 0) -> str:
    lines = []
    prefix = "  " * indent
    for key, value in state.items():
        if isinstance(value, dict):
            lines.append(f"{prefix}- **{key}**:")
            lines.append(_state_summary(value, indent + 1))
        else:
            lines.append(f"{prefix}- **{key}**: {value}")
    return "\n".join(lines)
