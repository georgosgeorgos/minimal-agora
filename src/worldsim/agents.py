from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from worldsim.models import (
    AgentConfig,
    AgentRole,
    Critique,
    EntityConfig,
    Proposal,
    Resolution,
    SimRule,
)


async def invoke_agent(
    agent: AgentConfig,
    workspace: Path,
    step: int,
    prompt: str,
    timeout: int = 300,
) -> str:
    cmd = [
        "claude",
        "-p", prompt,
        "--output-format", "text",
        "--max-turns", "5",
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(workspace),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        raise TimeoutError(f"Agent {agent.name} timed out after {timeout}s")

    if proc.returncode != 0:
        err = stderr.decode() if stderr else "unknown error"
        raise RuntimeError(f"Agent {agent.name} failed (exit {proc.returncode}): {err}")

    return stdout.decode().strip()


def _format_rules(rules: list[SimRule], agent_name: str, agent_role: str) -> str:
    applicable = [
        r for r in rules
        if not r.applies_to or agent_name in r.applies_to or agent_role in r.applies_to
    ]
    if not applicable:
        return ""
    lines = ["## Governing Rules", "These rules define the dynamics of this simulation. All proposals,",
             "critiques, and resolutions MUST respect these rules.", ""]
    for r in applicable:
        lines.append(f"**{r.name}**: {r.description}")
        lines.append("")
    return "\n".join(lines)


def build_interaction_context(
    entity: EntityConfig,
    all_entities: list[EntityConfig],
    state: dict,
    step: int,
) -> str:
    from worldsim.models import InteractionMode, TrajectoryType

    if entity.interaction.mode == InteractionMode.NEVER:
        return ""

    if entity.interaction.mode == InteractionMode.SCHEDULED and step % entity.interaction.every_n_steps != 0:
        return ""

    visible = entity.can_interact_with
    if not visible:
        return ""

    neighbors = [
        e for e in all_entities
        if e.name in visible and e.type == TrajectoryType.POPULATION
    ]
    if not neighbors:
        return ""

    lines = [
        "## Neighboring Populations",
        "You can observe the following civilizations. Consider their state",
        "when making your proposals — you may trade, ally, compete, or wage war.",
        "",
    ]

    populations = state.get("populations", {})
    for n in neighbors:
        n_state = populations.get(n.name, {})
        if n_state:
            lines.append(f"### {n.name.title()}")
            for k, v in n_state.items():
                lines.append(f"- **{k}**: {v}")
            lines.append("")
        else:
            lines.append(f"### {n.name.title()}")
            lines.append("- No observable state")
            lines.append("")

    return "\n".join(lines)


def build_actor_prompt(agent: AgentConfig, step: int, rules: list[SimRule] | None = None, interaction_context: str = "") -> str:
    rules_block = _format_rules(rules or [], agent.name, agent.role.value)
    interaction_block = f"\n{interaction_context}\n" if interaction_context else ""
    return f"""You are **{agent.name}**, an actor agent in a world simulation.

## Your Perspective
{agent.perspective}

{rules_block}{interaction_block}## Instructions
1. Read the current world state from `board/state.json`
2. Read the narrative history from `board/narrative.md`
3. Read the scenario description from `board/scenario.md`

Check if a wildcard event file exists at `board/wildcard_step_{step:03d}.json`.
If present, this is a major external shock (asteroid, pandemic, war, etc.)
that MUST be accounted for in your proposal. The wildcard's `state_impact`
suggests direct effects, but you should also reason about cascading consequences.

Based on the current state, any active wildcard, and your perspective, propose
what happens next in this time step. Think carefully about what changes are
most likely given your domain of influence.

4. Write your proposal as a JSON file to `proposals/step_{step:03d}_{agent.name}.json`

The JSON must have this structure:
```json
{{
  "agent": "{agent.name}",
  "role": "actor",
  "proposed_changes": {{
    "path.to.field": "new_value"
  }},
  "reasoning": "Why these changes happen",
  "confidence": 0.7
}}
```

The `proposed_changes` should be a flat or nested dict matching the structure
of state.json. Only include fields you want to change.
"""


def build_critic_prompt(agent: AgentConfig, step: int, rules: list[SimRule] | None = None) -> str:
    rules_block = _format_rules(rules or [], agent.name, agent.role.value)
    return f"""You are **{agent.name}**, a critic agent in a world simulation.

## Your Perspective
{agent.perspective}

{rules_block}
## Instructions
1. Read the current world state from `board/state.json`
2. Read the narrative history from `board/narrative.md`
3. Read ALL proposals in `proposals/` for step {step:03d}

Check if a wildcard event file exists at `board/wildcard_step_{step:03d}.json`.
If present, evaluate whether proposals adequately account for its impact.

Evaluate each proposal for plausibility, consistency, and realism.
Flag anything impossible, contradictory, or highly unlikely.

4. Write your critique as a JSON file to `critiques/step_{step:03d}_{agent.name}.json`

The JSON must have this structure:
```json
{{
  "agent": "{agent.name}",
  "target_proposals": ["proposal_agent_1", "proposal_agent_2"],
  "assessment": "Overall assessment of the proposals",
  "plausibility": 0.8,
  "issues": ["Issue 1", "Issue 2"]
}}
```
"""


def build_judge_prompt(agent: AgentConfig, step: int, rules: list[SimRule] | None = None) -> str:
    rules_block = _format_rules(rules or [], agent.name, agent.role.value)
    return f"""You are **{agent.name}**, the judge agent in a world simulation.

## Your Perspective
{agent.perspective}

{rules_block}
## Instructions
1. Read the current world state from `board/state.json`
2. Read the narrative history from `board/narrative.md`
3. Read ALL proposals in `proposals/` for step {step:03d}
4. Read ALL critiques in `critiques/` for step {step:03d}

Check if a wildcard event file exists at `board/wildcard_step_{step:03d}.json`.
If present, ensure the resolution fully accounts for the wildcard's impact,
including applying its `state_impact` and any cascading effects.

Synthesize the proposals and critiques into a single coherent outcome for this
time step. Resolve conflicts between proposals. Weight proposals by their
plausibility as assessed by critics.

5. Write your resolution as a JSON file to `resolutions/step_{step:03d}_resolution.json`

The JSON must have this structure:
```json
{{
  "state_delta": {{
    "path.to.field": "new_value"
  }},
  "narrative": "A paragraph describing what happened this step and why",
  "reasoning": "Why you resolved conflicts this way"
}}
```

The `state_delta` will be deep-merged into the current state. Only include
fields that change. The narrative should be written as a historical account,
not a technical description.
"""


def build_prompt(agent: AgentConfig, step: int, rules: list[SimRule] | None = None, interaction_context: str = "") -> str:
    if agent.role == AgentRole.ACTOR:
        return build_actor_prompt(agent, step, rules, interaction_context)
    elif agent.role == AgentRole.CRITIC:
        return build_critic_prompt(agent, step, rules)
    elif agent.role == AgentRole.JUDGE:
        return build_judge_prompt(agent, step, rules)
    raise ValueError(f"Unknown role: {agent.role}")


def parse_proposal(workspace: Path, agent_name: str, step: int) -> Proposal | None:
    path = workspace / "proposals" / f"step_{step:03d}_{agent_name}.json"
    if not path.exists():
        logger.warning("Proposal file missing: %s", path)
        return None
    try:
        with open(path) as f:
            return Proposal.model_validate_json(f.read())
    except (ValueError, OSError, KeyError) as e:
        logger.warning("Failed to parse proposal %s: %s", path.name, e)
        return None


def parse_critique(workspace: Path, agent_name: str, step: int) -> Critique | None:
    path = workspace / "critiques" / f"step_{step:03d}_{agent_name}.json"
    if not path.exists():
        logger.warning("Critique file missing: %s", path)
        return None
    try:
        with open(path) as f:
            return Critique.model_validate_json(f.read())
    except (ValueError, OSError, KeyError) as e:
        logger.warning("Failed to parse critique %s: %s", path.name, e)
        return None


def parse_resolution(workspace: Path, step: int) -> Resolution | None:
    path = workspace / "resolutions" / f"step_{step:03d}_resolution.json"
    if not path.exists():
        logger.warning("Resolution file missing: %s", path)
        return None
    try:
        with open(path) as f:
            return Resolution.model_validate_json(f.read())
    except (ValueError, OSError, KeyError) as e:
        logger.warning("Failed to parse resolution %s: %s", path.name, e)
        return None
