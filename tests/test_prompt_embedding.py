"""Tests for embedded state in agent prompts and text-based output parsing."""
from __future__ import annotations

import json

from minimal_agora.agents import (
    build_actor_prompt,
    build_constraint_evaluator_prompt,
    build_prompt,
    build_resolver_prompt,
    parse_critique_from_text,
    parse_proposal_from_text,
    parse_resolution_from_text,
)
from minimal_agora.models import AgentConfig, AgentRole, SimRule
from minimal_agora.providers.subprocess_provider import ClaudeSubprocessProvider


def _make_agent(
    name: str = "test_actor",
    role: AgentRole = AgentRole.ACTOR,
    perspective: str = "Test perspective",
) -> AgentConfig:
    return AgentConfig(role=role, name=name, perspective=perspective)


SAMPLE_STATE = {"time": {"step": 3}, "population": 1000, "resources": {"food": 50}}
SAMPLE_NARRATIVE = "## Step 1\nThings happened.\n\n## Step 2\nMore things happened."
SAMPLE_WILDCARD = {
    "name": "meteor_strike",
    "description": "A large meteor hits the planet",
    "state_impact": {"resources": {"food": -20}},
}
SAMPLE_PROPOSALS = [
    {
        "agent": "actor_1",
        "role": "actor",
        "proposed_changes": {"population": 1100},
        "reasoning": "Growth period",
        "confidence": 0.8,
    },
]
SAMPLE_CRITIQUES = [
    {
        "agent": "critic_1",
        "target_proposals": ["actor_1"],
        "assessment": "Plausible",
        "plausibility": 0.9,
        "issues": [],
    },
]


class TestActorPromptEmbedsState:
    def test_state_json_in_prompt(self) -> None:
        agent = _make_agent()
        prompt = build_actor_prompt(agent, step=3, state=SAMPLE_STATE, narrative=SAMPLE_NARRATIVE)
        assert json.dumps(SAMPLE_STATE, indent=2) in prompt

    def test_narrative_in_prompt(self) -> None:
        agent = _make_agent()
        prompt = build_actor_prompt(agent, step=3, state=SAMPLE_STATE, narrative=SAMPLE_NARRATIVE)
        assert "Things happened." in prompt
        assert "More things happened." in prompt

    def test_wildcard_in_prompt(self) -> None:
        agent = _make_agent()
        prompt = build_actor_prompt(
            agent, step=3, state=SAMPLE_STATE, narrative=SAMPLE_NARRATIVE, wildcard=SAMPLE_WILDCARD,
        )
        assert "meteor_strike" in prompt
        assert "A large meteor hits the planet" in prompt
        assert "MUST be accounted for" in prompt

    def test_no_file_read_instructions_when_embedded(self) -> None:
        agent = _make_agent()
        prompt = build_actor_prompt(agent, step=3, state=SAMPLE_STATE, narrative=SAMPLE_NARRATIVE)
        assert "Read the current world state from" not in prompt
        assert "board/state.json" not in prompt

    def test_asks_for_json_stdout_when_embedded(self) -> None:
        agent = _make_agent()
        prompt = build_actor_prompt(agent, step=3, state=SAMPLE_STATE, narrative=SAMPLE_NARRATIVE)
        assert "Respond with ONLY a JSON object" in prompt

    def test_fallback_without_state(self) -> None:
        agent = _make_agent()
        prompt = build_actor_prompt(agent, step=3)
        assert "Read the current world state from `board/state.json`" in prompt
        assert "Write your proposal as a JSON file" in prompt

    def test_rules_still_included(self) -> None:
        agent = _make_agent()
        rules = [SimRule(name="Conservation", description="Energy is conserved")]
        prompt = build_actor_prompt(
            agent, step=3, rules=rules, state=SAMPLE_STATE, narrative=SAMPLE_NARRATIVE,
        )
        assert "Conservation" in prompt
        assert "Energy is conserved" in prompt

    def test_diversity_lens_included(self) -> None:
        agent = _make_agent()
        prompt = build_actor_prompt(
            agent, step=3, state=SAMPLE_STATE, narrative=SAMPLE_NARRATIVE, trajectory_id=2,
        )
        assert "trajectory 2" in prompt


class TestConstraintEvaluatorPromptEmbedsProposals:
    def test_proposals_in_prompt(self) -> None:
        agent = _make_agent(name="critic_1", role=AgentRole.CONSTRAINT_EVALUATOR)
        prompt = build_constraint_evaluator_prompt(
            agent, step=3, state=SAMPLE_STATE, narrative=SAMPLE_NARRATIVE,
            proposals=SAMPLE_PROPOSALS,
        )
        assert "actor_1" in prompt
        assert "Growth period" in prompt

    def test_state_in_prompt(self) -> None:
        agent = _make_agent(name="critic_1", role=AgentRole.CONSTRAINT_EVALUATOR)
        prompt = build_constraint_evaluator_prompt(
            agent, step=3, state=SAMPLE_STATE, narrative=SAMPLE_NARRATIVE,
            proposals=SAMPLE_PROPOSALS,
        )
        assert json.dumps(SAMPLE_STATE, indent=2) in prompt

    def test_no_file_instructions_when_embedded(self) -> None:
        agent = _make_agent(name="critic_1", role=AgentRole.CONSTRAINT_EVALUATOR)
        prompt = build_constraint_evaluator_prompt(
            agent, step=3, state=SAMPLE_STATE, narrative=SAMPLE_NARRATIVE,
            proposals=SAMPLE_PROPOSALS,
        )
        assert "Read the current world state from" not in prompt
        assert "Read ALL proposals" not in prompt

    def test_fallback_without_state(self) -> None:
        agent = _make_agent(name="critic_1", role=AgentRole.CONSTRAINT_EVALUATOR)
        prompt = build_constraint_evaluator_prompt(agent, step=3)
        assert "Read the current world state from `board/state.json`" in prompt


class TestResolverPromptEmbedsAll:
    def test_proposals_and_critiques_in_prompt(self) -> None:
        agent = _make_agent(name="judge_1", role=AgentRole.RESOLVER)
        prompt = build_resolver_prompt(
            agent, step=3, state=SAMPLE_STATE, narrative=SAMPLE_NARRATIVE,
            proposals=SAMPLE_PROPOSALS, critiques=SAMPLE_CRITIQUES,
        )
        assert "actor_1" in prompt
        assert "Growth period" in prompt
        assert "Plausible" in prompt
        assert "critic_1" in prompt

    def test_state_in_prompt(self) -> None:
        agent = _make_agent(name="judge_1", role=AgentRole.RESOLVER)
        prompt = build_resolver_prompt(
            agent, step=3, state=SAMPLE_STATE, narrative=SAMPLE_NARRATIVE,
            proposals=SAMPLE_PROPOSALS, critiques=SAMPLE_CRITIQUES,
        )
        assert json.dumps(SAMPLE_STATE, indent=2) in prompt

    def test_wildcard_in_prompt(self) -> None:
        agent = _make_agent(name="judge_1", role=AgentRole.RESOLVER)
        prompt = build_resolver_prompt(
            agent, step=3, state=SAMPLE_STATE, narrative=SAMPLE_NARRATIVE,
            proposals=SAMPLE_PROPOSALS, critiques=SAMPLE_CRITIQUES, wildcard=SAMPLE_WILDCARD,
        )
        assert "meteor_strike" in prompt

    def test_no_file_instructions_when_embedded(self) -> None:
        agent = _make_agent(name="judge_1", role=AgentRole.RESOLVER)
        prompt = build_resolver_prompt(
            agent, step=3, state=SAMPLE_STATE, narrative=SAMPLE_NARRATIVE,
            proposals=SAMPLE_PROPOSALS, critiques=SAMPLE_CRITIQUES,
        )
        assert "Read the current world state from" not in prompt
        assert "Read ALL proposals" not in prompt
        assert "Read ALL critiques" not in prompt

    def test_fallback_without_state(self) -> None:
        agent = _make_agent(name="judge_1", role=AgentRole.RESOLVER)
        prompt = build_resolver_prompt(agent, step=3)
        assert "Read the current world state from `board/state.json`" in prompt


class TestBuildPromptPassesKwargs:
    def test_actor_receives_state(self) -> None:
        agent = _make_agent()
        prompt = build_prompt(agent, step=3, state=SAMPLE_STATE, narrative=SAMPLE_NARRATIVE)
        assert json.dumps(SAMPLE_STATE, indent=2) in prompt

    def test_critic_receives_proposals(self) -> None:
        agent = _make_agent(name="critic_1", role=AgentRole.CONSTRAINT_EVALUATOR)
        prompt = build_prompt(
            agent, step=3, state=SAMPLE_STATE, narrative=SAMPLE_NARRATIVE,
            proposals=SAMPLE_PROPOSALS,
        )
        assert "Growth period" in prompt

    def test_judge_receives_all(self) -> None:
        agent = _make_agent(name="judge_1", role=AgentRole.RESOLVER)
        prompt = build_prompt(
            agent, step=3, state=SAMPLE_STATE, narrative=SAMPLE_NARRATIVE,
            proposals=SAMPLE_PROPOSALS, critiques=SAMPLE_CRITIQUES,
        )
        assert "Growth period" in prompt
        assert "Plausible" in prompt


class TestParseProposalFromText:
    def test_valid_json(self) -> None:
        text = json.dumps({
            "agent": "test_actor",
            "role": "actor",
            "proposed_changes": {"x": 1},
            "reasoning": "test",
            "confidence": 0.8,
        })
        result = parse_proposal_from_text(text, "test_actor")
        assert result is not None
        assert result.agent == "test_actor"
        assert result.proposed_changes == {"x": 1}

    def test_json_in_markdown_block(self) -> None:
        text = (
            "Here is my proposal:\n"
            "```json\n"
            '{"agent": "test_actor", "role": "actor", '
            '"proposed_changes": {"y": 2}, "reasoning": "test", "confidence": 0.9}\n'
            "```\n"
            "That's all."
        )
        result = parse_proposal_from_text(text, "test_actor")
        assert result is not None
        assert result.proposed_changes == {"y": 2}

    def test_invalid_text(self) -> None:
        result = parse_proposal_from_text("not json at all", "test_actor")
        assert result is None

    def test_valid_json_wrong_schema(self) -> None:
        result = parse_proposal_from_text('{"foo": "bar"}', "test_actor")
        assert result is None


class TestParseCritiqueFromText:
    def test_valid_json(self) -> None:
        text = json.dumps({
            "agent": "critic_1",
            "target_proposals": ["actor_1"],
            "assessment": "Good",
            "plausibility": 0.9,
            "issues": [],
        })
        result = parse_critique_from_text(text, "critic_1")
        assert result is not None
        assert result.agent == "critic_1"

    def test_invalid_text(self) -> None:
        assert parse_critique_from_text("garbage", "critic_1") is None


class TestParseResolutionFromText:
    def test_valid_json(self) -> None:
        text = json.dumps({
            "state_delta": {"x": 1},
            "narrative": "Things changed.",
            "reasoning": "Because.",
        })
        result = parse_resolution_from_text(text)
        assert result is not None
        assert result.state_delta == {"x": 1}

    def test_json_in_code_block(self) -> None:
        text = (
            "```\n"
            '{"state_delta": {"a": 2}, "narrative": "Done.", "reasoning": "OK."}\n'
            "```"
        )
        result = parse_resolution_from_text(text)
        assert result is not None
        assert result.state_delta == {"a": 2}

    def test_invalid_text(self) -> None:
        assert parse_resolution_from_text("no json here") is None


class TestMaxTurnsDefault:
    def test_default_is_1(self) -> None:
        provider = ClaudeSubprocessProvider()
        assert provider.max_turns == 1

    def test_custom_max_turns(self) -> None:
        provider = ClaudeSubprocessProvider(max_turns=10)
        assert provider.max_turns == 10
