"""Prompt and response interface for multi-step simulation batches."""

from __future__ import annotations

import json
import re

from minimal_agora.models import (
    AgentConfig,
    AgentRole,
    BatchCritique,
    BatchProposal,
    BatchResolution,
    SimRule,
)

BatchOutput = BatchProposal | BatchCritique | BatchResolution


def build_batch_prompt(
    agent: AgentConfig,
    *,
    step_numbers: list[int],
    rules: list[SimRule],
    state: dict,
    narrative: str,
    trajectory_id: int = 0,
    proposals: list[dict] | None = None,
    critiques: list[dict] | None = None,
) -> str:
    """Build the role-specific prompt for one contiguous batch."""
    if not step_numbers:
        raise ValueError("step_numbers must not be empty")
    expected = list(range(step_numbers[0], step_numbers[-1] + 1))
    if step_numbers != expected:
        raise ValueError("step_numbers must be contiguous")

    start, end = step_numbers[0], step_numbers[-1]
    shared = (
        f"## Simulate Steps {start}-{end}\n\n"
        f"Trajectory: {trajectory_id}\n\n"
        f"## State Before Step {start}\n```json\n{json.dumps(state, indent=2)}\n```\n\n"
        f"## Narrative History\n{narrative or '(No narrative yet.)'}\n\n"
        f"{_format_rules(rules, agent)}"
    )

    if agent.role == AgentRole.ACTOR:
        example = json.dumps(
            {
                "steps": [
                    {
                        "step_number": start,
                        "agent": agent.name,
                        "role": "actor",
                        "proposed_changes": {"path.to.field": "new_value"},
                        "reasoning": "brief reason",
                        "confidence": 0.7,
                    }
                ],
            }
        )
        return (
            f"You are **{agent.name}**, a batch actor agent in a world simulation.\n\n"
            f"## Your Perspective\n{agent.perspective}\n\n"
            f"{shared}"
            "## Instructions\n"
            "Simulate every requested step sequentially. Treat each proposed value as the "
            "absolute value to deep-merge at that step, and account for your own earlier "
            "changes when planning later steps. Return exactly one entry per step.\n\n"
            "Respond with ONLY JSON in this form:\n"
            f"{example}\n"
        )

    proposals_json = json.dumps(proposals or [], indent=2)
    if agent.role == AgentRole.CONSTRAINT_EVALUATOR:
        example = json.dumps(
            {
                "steps": [
                    {
                        "step_number": start,
                        "agent": agent.name,
                        "target_proposals": ["actor"],
                        "assessment": "brief assessment",
                        "plausibility": 0.8,
                        "scores": {"physical": 0.9},
                        "issues": [],
                    }
                ],
            }
        )
        return (
            f"You are **{agent.name}**, a batch constraint evaluator agent in a world simulation.\n\n"
            f"## Your Perspective\n{agent.perspective}\n\n"
            f"{shared}"
            f"## Step-Indexed Actor Proposals\n```json\n{proposals_json}\n```\n\n"
            "## Instructions\n"
            "Evaluate the proposals at every requested step for physical possibility, "
            "consistency, pacing, and rule compliance. Return exactly one entry per step.\n\n"
            "Respond with ONLY JSON in this form:\n"
            f"{example}\n"
        )

    if agent.role == AgentRole.RESOLVER:
        critiques_json = json.dumps(critiques or [], indent=2)
        example = json.dumps(
            {
                "steps": [
                    {
                        "step_number": start,
                        "state_delta": {"path.to.field": "new_value"},
                        "narrative": "what happened",
                        "reasoning": "brief rationale",
                    }
                ],
            }
        )
        return (
            f"You are **{agent.name}**, the batch resolver agent in a world simulation.\n\n"
            f"## Your Perspective\n{agent.perspective}\n\n"
            f"{shared}"
            f"## Step-Indexed Actor Proposals\n```json\n{proposals_json}\n```\n\n"
            f"## Step-Indexed Constraint Evaluations\n```json\n{critiques_json}\n```\n\n"
            "## Instructions\n"
            "Resolve every requested step sequentially. Mentally deep-merge each earlier "
            "state_delta before resolving the next step. Return exactly one entry per step; "
            "each state_delta contains absolute replacement values, not arithmetic deltas.\n\n"
            "Respond with ONLY JSON in this form:\n"
            f"{example}\n"
        )

    raise ValueError(f"Unsupported batch role: {agent.role}")


def parse_batch_output(role: AgentRole, text: str) -> BatchOutput | None:
    """Parse a role-specific batch response from plain or fenced JSON."""
    extracted = _extract_json(text)
    if extracted is None:
        return None
    try:
        if role == AgentRole.ACTOR:
            return BatchProposal.model_validate_json(extracted)
        if role == AgentRole.CONSTRAINT_EVALUATOR:
            return BatchCritique.model_validate_json(extracted)
        if role == AgentRole.RESOLVER:
            return BatchResolution.model_validate_json(extracted)
    except ValueError:
        return None
    return None


def _format_rules(rules: list[SimRule], agent: AgentConfig) -> str:
    applicable = [
        rule
        for rule in rules
        if not rule.applies_to
        or agent.name in rule.applies_to
        or agent.role.value in rule.applies_to
    ]
    if not applicable:
        return ""
    lines = ["## Governing Rules"]
    lines.extend(f"- **{rule.name}**: {rule.description}" for rule in applicable)
    return "\n".join(lines) + "\n\n"


def _extract_json(text: str) -> str | None:
    text = text.strip()
    try:
        json.loads(text)
        return text
    except (json.JSONDecodeError, ValueError):
        pass
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if not match:
        return None
    candidate = match.group(1).strip()
    try:
        json.loads(candidate)
        return candidate
    except (json.JSONDecodeError, ValueError):
        return None
