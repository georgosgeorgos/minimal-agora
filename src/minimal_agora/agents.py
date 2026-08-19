from __future__ import annotations

import json
import re
from pathlib import Path

import structlog

from minimal_agora.models import (
    AgentConfig,
    AgentRole,
    Critique,
    EntityConfig,
    Proposal,
    ResamplingScore,
    Resolution,
    SimRule,
)
from minimal_agora.providers.protocol import AgentInvocationResult, AgentProvider
from minimal_agora.providers.subprocess_provider import ClaudeSubprocessProvider

logger = structlog.stdlib.get_logger(__name__)

_default_provider: AgentProvider = ClaudeSubprocessProvider()


def set_default_provider(provider: AgentProvider) -> None:
    """Set the module-level default provider for all agent invocations."""
    global _default_provider
    _default_provider = provider


def get_default_provider() -> AgentProvider:
    """Return the current module-level default provider."""
    return _default_provider


async def invoke_agent(
    agent: AgentConfig,
    workspace: Path,
    step: int,
    prompt: str,
    timeout: int = 300,
    provider: AgentProvider | None = None,
) -> AgentInvocationResult:
    active = provider or _default_provider

    logger.debug(
        "provider.invoke",
        agent=agent.name,
        step=step,
        provider_type=type(active).__name__,
    )

    result = await active.invoke(prompt, workspace, timeout)

    logger.debug(
        "provider.invoke.done",
        agent=agent.name,
        step=step,
        tokens_used=result.tokens_used,
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )

    return result


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


def _get_entity_state(state: dict, entity: EntityConfig) -> dict:
    if not entity.state_prefix:
        return {}
    keys = entity.state_prefix.split(".")
    current = state
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return {}
        current = current[key]
    return current if isinstance(current, dict) else {}


def build_interaction_context(
    entity: EntityConfig,
    all_entities: list[EntityConfig],
    state: dict,
    step: int,
) -> str:
    from minimal_agora.models import InteractionMode, TrajectoryType

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
        "## Neighboring Entities",
        "You can observe the following entities. Consider their state",
        "when making your proposals — interactions may include competition,",
        "cooperation, conflict, trade, or other dynamics.",
        "",
    ]

    for n in neighbors:
        n_state = _get_entity_state(state, n)
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


DIVERSITY_LENSES = [
    "Focus on the most probable outcome given current conditions.",
    "Explore unlikely but plausible outcomes — what if a low-probability event shapes this step?",
    "Emphasize long-term consequences over short-term effects.",
    "Consider second-order effects: how do changes in one domain cascade to others?",
    "Prioritize stability and equilibrium — what resists change?",
    "Focus on competition and conflict as drivers of change.",
    "Emphasize cooperation, trade, and mutual benefit as drivers.",
    "Consider environmental and resource constraints as primary shapers.",
    "Explore the role of random variation and contingency.",
    "Focus on internal dynamics: how do divisions within a system drive change?",
]


def _diversity_prefix(trajectory_id: int) -> str:
    lens = DIVERSITY_LENSES[trajectory_id % len(DIVERSITY_LENSES)]
    return f"**Exploration lens (trajectory {trajectory_id})**: {lens}"


def _format_wildcard(wildcard: dict | None) -> str:
    if not wildcard:
        return ""
    impact = wildcard.get("state_impact", {})
    impact_str = f"\nImpact: {json.dumps(impact, indent=2)}" if impact else ""
    return (
        f"\n## Active Wildcard Event\n"
        f"**{wildcard['name']}**: {wildcard.get('description', '')}{impact_str}\n"
        f"This is a major external shock that MUST be accounted for in your proposal.\n"
    )


def build_actor_prompt(
    agent: AgentConfig,
    step: int,
    rules: list[SimRule] | None = None,
    interaction_context: str = "",
    trajectory_id: int | None = None,
    state: dict | None = None,
    narrative: str | None = None,
    wildcard: dict | None = None,
) -> str:
    logger.debug(
        "prompt.build_actor",
        agent=agent.name,
        step=step,
        has_wildcard=wildcard is not None,
        has_interaction_context=bool(interaction_context),
        embedded_state=state is not None,
    )
    rules_block = _format_rules(rules or [], agent.name, agent.role.value)
    interaction_block = f"\n{interaction_context}\n" if interaction_context else ""
    diversity_block = f"\n{_diversity_prefix(trajectory_id)}\n" if trajectory_id is not None else ""
    wildcard_block = _format_wildcard(wildcard)

    if state is not None:
        state_section = (
            f"## Simulation Step {step}\n\n"
            f"## Current World State\n```json\n{json.dumps(state, indent=2)}\n```\n"
        )
        narrative_section = f"\n## Narrative History\n{narrative or '(No narrative yet.)'}\n"
        instructions = (
            f"{wildcard_block}"
            f"\n## Instructions\n"
            f"Based on the current state, any active wildcard, and your perspective, propose\n"
            f"what happens next in this time step. Think carefully about what changes are\n"
            f"most likely given your domain of influence.\n\n"
            f"Respond with ONLY a JSON object (no markdown fences, no explanation):\n"
            f'{{"agent": "{agent.name}", "role": "actor", '
            f'"proposed_changes": {{"path.to.field": "new_value"}}, '
            f'"reasoning": "Why these changes happen", "confidence": 0.7}}\n\n'
            f"The `proposed_changes` should be a flat or nested dict matching the structure\n"
            f"of the world state. Only include fields you want to change.\n"
        )
    else:
        state_section = ""
        narrative_section = ""
        instructions = (
            f"## Instructions\n"
            f"1. Read the current world state from `board/state.json`\n"
            f"2. Read the narrative history from `board/narrative.md`\n"
            f"3. Read the scenario description from `board/scenario.md`\n\n"
            f"Check if a wildcard event file exists at `board/wildcard_step_{step:03d}.json`.\n"
            f"If present, this is a major external shock (asteroid, pandemic, war, etc.)\n"
            f"that MUST be accounted for in your proposal. The wildcard's `state_impact`\n"
            f"suggests direct effects, but you should also reason about cascading consequences.\n\n"
            f"Based on the current state, any active wildcard, and your perspective, propose\n"
            f"what happens next in this time step. Think carefully about what changes are\n"
            f"most likely given your domain of influence.\n\n"
            f"4. Write your proposal as a JSON file to `proposals/step_{step:03d}_{agent.name}.json`\n\n"
            f"The JSON must have this structure:\n"
            f"```json\n"
            f"{{\n"
            f'  "agent": "{agent.name}",\n'
            f'  "role": "actor",\n'
            f'  "proposed_changes": {{\n'
            f'    "path.to.field": "new_value"\n'
            f"  }},\n"
            f'  "reasoning": "Why these changes happen",\n'
            f'  "confidence": 0.7\n'
            f"}}\n"
            f"```\n\n"
            f"The `proposed_changes` should be a flat or nested dict matching the structure\n"
            f"of state.json. Only include fields you want to change.\n"
        )

    return (
        f"You are **{agent.name}**, an actor agent in a world simulation.\n"
        f"{diversity_block}\n"
        f"## Your Perspective\n"
        f"{agent.perspective}\n\n"
        f"{state_section}"
        f"{narrative_section}"
        f"{rules_block}{interaction_block}"
        f"{instructions}"
    )


def build_critic_prompt(
    agent: AgentConfig,
    step: int,
    rules: list[SimRule] | None = None,
    state: dict | None = None,
    narrative: str | None = None,
    proposals: list[dict] | None = None,
    wildcard: dict | None = None,
) -> str:
    logger.debug(
        "prompt.build_critic",
        agent=agent.name,
        step=step,
        embedded_state=state is not None,
    )
    rules_block = _format_rules(rules or [], agent.name, agent.role.value)
    wildcard_block = _format_wildcard(wildcard)

    if state is not None:
        proposals_json = json.dumps(proposals or [], indent=2)
        return (
            f"You are **{agent.name}**, a critic agent in a world simulation.\n\n"
            f"## Your Perspective\n{agent.perspective}\n\n"
            f"## Current World State\n```json\n{json.dumps(state, indent=2)}\n```\n\n"
            f"## Narrative History\n{narrative or '(No narrative yet.)'}\n\n"
            f"## Proposals for Step {step}\n```json\n{proposals_json}\n```\n\n"
            f"{rules_block}"
            f"{wildcard_block}"
            f"\n## Instructions\n"
            f"Evaluate each proposal for plausibility, consistency, and realism.\n"
            f"Flag anything impossible, contradictory, or highly unlikely.\n\n"
            f"Respond with ONLY a JSON object (no markdown fences, no explanation):\n"
            f'{{"agent": "{agent.name}", "target_proposals": ["agent1", "agent2"], '
            f'"assessment": "Overall assessment", "plausibility": 0.8, '
            f'"issues": ["Issue 1", "Issue 2"]}}\n'
        )

    return (
        f"You are **{agent.name}**, a critic agent in a world simulation.\n\n"
        f"## Your Perspective\n{agent.perspective}\n\n"
        f"{rules_block}\n"
        f"## Instructions\n"
        f"1. Read the current world state from `board/state.json`\n"
        f"2. Read the narrative history from `board/narrative.md`\n"
        f"3. Read ALL proposals in `proposals/` for step {step:03d}\n\n"
        f"Check if a wildcard event file exists at `board/wildcard_step_{step:03d}.json`.\n"
        f"If present, evaluate whether proposals adequately account for its impact.\n\n"
        f"Evaluate each proposal for plausibility, consistency, and realism.\n"
        f"Flag anything impossible, contradictory, or highly unlikely.\n\n"
        f"4. Write your critique as a JSON file to `critiques/step_{step:03d}_{agent.name}.json`\n\n"
        f"The JSON must have this structure:\n"
        f"```json\n"
        f"{{\n"
        f'  "agent": "{agent.name}",\n'
        f'  "target_proposals": ["proposal_agent_1", "proposal_agent_2"],\n'
        f'  "assessment": "Overall assessment of the proposals",\n'
        f'  "plausibility": 0.8,\n'
        f'  "issues": ["Issue 1", "Issue 2"]\n'
        f"}}\n"
        f"```\n"
    )


def build_judge_prompt(
    agent: AgentConfig,
    step: int,
    rules: list[SimRule] | None = None,
    state: dict | None = None,
    narrative: str | None = None,
    proposals: list[dict] | None = None,
    critiques: list[dict] | None = None,
    wildcard: dict | None = None,
) -> str:
    logger.debug(
        "prompt.build_judge",
        agent=agent.name,
        step=step,
        embedded_state=state is not None,
    )
    rules_block = _format_rules(rules or [], agent.name, agent.role.value)
    wildcard_block = _format_wildcard(wildcard)

    if state is not None:
        proposals_json = json.dumps(proposals or [], indent=2)
        critiques_json = json.dumps(critiques or [], indent=2)
        return (
            f"You are **{agent.name}**, the judge agent in a world simulation.\n\n"
            f"## Your Perspective\n{agent.perspective}\n\n"
            f"## Current World State\n```json\n{json.dumps(state, indent=2)}\n```\n\n"
            f"## Narrative History\n{narrative or '(No narrative yet.)'}\n\n"
            f"## Proposals for Step {step}\n```json\n{proposals_json}\n```\n\n"
            f"## Critiques for Step {step}\n```json\n{critiques_json}\n```\n\n"
            f"{rules_block}"
            f"{wildcard_block}"
            f"\n## Instructions\n"
            f"Synthesize the proposals and critiques into a single coherent outcome for this\n"
            f"time step. Resolve conflicts between proposals. Weight proposals by their\n"
            f"plausibility as assessed by critics.\n\n"
            f"The `state_delta` will be deep-merged into the current state. Only include\n"
            f"fields that change. The narrative should be written as a historical account,\n"
            f"not a technical description.\n\n"
            f"Respond with ONLY a JSON object (no markdown fences, no explanation):\n"
            f'{{"state_delta": {{"path.to.field": "new_value"}}, '
            f'"narrative": "A paragraph describing what happened", '
            f'"reasoning": "Why you resolved conflicts this way"}}\n'
        )

    return (
        f"You are **{agent.name}**, the judge agent in a world simulation.\n\n"
        f"## Your Perspective\n{agent.perspective}\n\n"
        f"{rules_block}\n"
        f"## Instructions\n"
        f"1. Read the current world state from `board/state.json`\n"
        f"2. Read the narrative history from `board/narrative.md`\n"
        f"3. Read ALL proposals in `proposals/` for step {step:03d}\n"
        f"4. Read ALL critiques in `critiques/` for step {step:03d}\n\n"
        f"Check if a wildcard event file exists at `board/wildcard_step_{step:03d}.json`.\n"
        f"If present, ensure the resolution fully accounts for the wildcard's impact,\n"
        f"including applying its `state_impact` and any cascading effects.\n\n"
        f"Synthesize the proposals and critiques into a single coherent outcome for this\n"
        f"time step. Resolve conflicts between proposals. Weight proposals by their\n"
        f"plausibility as assessed by critics.\n\n"
        f"5. Write your resolution as a JSON file to `resolutions/step_{step:03d}_resolution.json`\n\n"
        f"The JSON must have this structure:\n"
        f"```json\n"
        f"{{\n"
        f'  "state_delta": {{\n'
        f'    "path.to.field": "new_value"\n'
        f"  }},\n"
        f'  "narrative": "A paragraph describing what happened this step and why",\n'
        f'  "reasoning": "Why you resolved conflicts this way"\n'
        f"}}\n"
        f"```\n\n"
        f"The `state_delta` will be deep-merged into the current state. Only include\n"
        f"fields that change. The narrative should be written as a historical account,\n"
        f"not a technical description.\n"
    )


def build_resampling_critic_prompt(
    state_or_criteria: dict | list[str],
    narrative_or_step: str | int | None = None,
    trajectory_summaries: list[dict] | None = None,
    *,
    step: int | None = None,
) -> str:
    if step is not None and narrative_or_step is None:
        narrative_or_step = step
    if isinstance(state_or_criteria, dict):
        state_json = json.dumps(state_or_criteria, indent=2)
        summaries_json = json.dumps(trajectory_summaries or [], indent=2)
        narrative = narrative_or_step
        return (
            "You are a **resampling critic** in a particle-filtering world simulation.\n\n"
            "Your job is to evaluate a set of parallel trajectories and decide which are most\n"
            "promising (should be duplicated) and which are least promising (should be pruned).\n\n"
            f"## Current World State\n```json\n{state_json}\n```\n\n"
            f"## Narrative So Far\n{narrative}\n\n"
            "## Trajectory Summaries\n"
            "Each entry describes one trajectory's recent progress, fitness, and outcome so far.\n"
            f"```json\n{summaries_json}\n```\n\n"
            "## Instructions\n"
            "Evaluate each trajectory on:\n"
            "- **Plausibility**: Is the trajectory's progression realistic and internally consistent?\n"
            "- **Diversity**: Does it explore a meaningfully different region of the outcome space?\n"
            "- **Promise**: Is it trending toward an interesting or informative outcome?\n\n"
            "Return your assessment as JSON on stdout with this structure:\n"
            '```json\n'
            '{\n'
            '  "scores": [\n'
            '    {\n'
            '      "trajectory_id": 0,\n'
            '      "score": 0.85,\n'
            '      "reasoning": "Why this trajectory is or isn\'t promising"\n'
            '    }\n'
            '  ],\n'
            '  "recommendation": "Which trajectories to duplicate and which to prune",\n'
            '  "overall_assessment": "Brief assessment of trajectory diversity and quality"\n'
            '}\n'
            '```\n\n'
            "Score each trajectory from 0.0 (prune) to 1.0 (duplicate). Higher scores mean\n"
            "the trajectory should receive more copies in the resampled population.\n"
        )
    criteria = state_or_criteria
    step = narrative_or_step
    criteria_lines = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(criteria))
    return f"""You are a **resampling critic** evaluating trajectory quality at step {step}.

## Instructions
1. Read the current world state from `board/state.json`
2. Read the narrative history from `board/narrative.md`
3. For each criterion below, score 0 (no) or 1 (yes):

{criteria_lines}

4. Write your result as a JSON file to `critiques/resample_step_{step:03d}.json`

The JSON must have this structure:
```json
{{
  "scores": [0, 1, 1, ...],
  "total": 4,
  "notes": "Brief explanation of your scoring"
}}
```

The `scores` array must have exactly {len(criteria)} elements (one per criterion above).
The `total` must equal the sum of the scores array.
"""


def build_prompt(
    agent: AgentConfig,
    step: int,
    rules: list[SimRule] | None = None,
    interaction_context: str = "",
    trajectory_id: int | None = None,
    **kwargs: object,
) -> str:
    if agent.role == AgentRole.ACTOR:
        return build_actor_prompt(agent, step, rules, interaction_context, trajectory_id, **kwargs)
    elif agent.role == AgentRole.CRITIC:
        return build_critic_prompt(agent, step, rules, **kwargs)
    elif agent.role == AgentRole.JUDGE:
        return build_judge_prompt(agent, step, rules, **kwargs)
    elif agent.role == AgentRole.RESAMPLING_CRITIC:
        raise ValueError(
            "RESAMPLING_CRITIC must be invoked via build_resampling_critic_prompt() directly, "
            "not through build_prompt(), because it requires state, narrative, and trajectory_summaries parameters"
        )
    raise ValueError(f"Unknown role: {agent.role}")


def parse_proposal(workspace: Path, agent_name: str, step: int) -> Proposal | None:
    path = workspace / "proposals" / f"step_{step:03d}_{agent_name}.json"
    if not path.exists():
        logger.warning("Proposal file missing: %s", path)
        return None
    try:
        with open(path) as f:
            result = Proposal.model_validate_json(f.read())
        logger.debug("parse.proposal.success", agent_name=agent_name, step=step)
        return result
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
            result = Critique.model_validate_json(f.read())
        logger.debug("parse.critique.success", agent_name=agent_name, step=step)
        return result
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
            result = Resolution.model_validate_json(f.read())
        logger.debug("parse.resolution.success", step=step)
        return result
    except (ValueError, OSError, KeyError) as e:
        logger.warning("Failed to parse resolution %s: %s", path.name, e)
        return None


def _extract_json_from_text(text: str) -> str | None:
    """Try to extract JSON from text, handling markdown code blocks."""
    text = text.strip()
    try:
        json.loads(text)
        return text
    except (json.JSONDecodeError, ValueError):
        pass
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        candidate = match.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except (json.JSONDecodeError, ValueError):
            pass
    return None


def parse_proposal_from_text(text: str, agent_name: str) -> Proposal | None:
    extracted = _extract_json_from_text(text)
    if extracted is None:
        logger.warning("parse.proposal_from_text.no_json", agent_name=agent_name)
        return None
    try:
        return Proposal.model_validate_json(extracted)
    except (ValueError, KeyError) as e:
        logger.warning("parse.proposal_from_text.invalid", agent_name=agent_name, error=str(e))
        return None


def parse_critique_from_text(text: str, agent_name: str) -> Critique | None:
    extracted = _extract_json_from_text(text)
    if extracted is None:
        logger.warning("parse.critique_from_text.no_json", agent_name=agent_name)
        return None
    try:
        return Critique.model_validate_json(extracted)
    except (ValueError, KeyError) as e:
        logger.warning("parse.critique_from_text.invalid", agent_name=agent_name, error=str(e))
        return None


def parse_resolution_from_text(text: str) -> Resolution | None:
    extracted = _extract_json_from_text(text)
    if extracted is None:
        logger.warning("parse.resolution_from_text.no_json")
        return None
    try:
        return Resolution.model_validate_json(extracted)
    except (ValueError, KeyError) as e:
        logger.warning("parse.resolution_from_text.invalid", error=str(e))
        return None


def parse_resampling_score(workspace: Path, step: int, trajectory_id: int) -> ResamplingScore | None:
    path = workspace / "critiques" / f"resample_step_{step:03d}.json"
    if not path.exists():
        logger.warning("Resampling score file missing: %s", path)
        return None
    try:
        import json
        with open(path) as f:
            data = json.load(f)
        return ResamplingScore(
            trajectory_id=trajectory_id,
            scores=data["scores"],
            total=data["total"],
            notes=data.get("notes", ""),
        )
    except (ValueError, OSError, KeyError) as e:
        logger.warning("Failed to parse resampling score %s: %s", path.name, e)
        return None
