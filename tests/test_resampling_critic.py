from minimal_agora.agents import build_resampling_critic_prompt
from minimal_agora.models import AgentConfig, AgentRole


def _sample_state():
    return {
        "life": {"complexity": "multicellular", "photosynthesis": True},
        "environment": {"oxygen": "moderate", "temperature": "warm"},
    }


def _sample_summaries():
    return [
        {
            "trajectory_id": 0,
            "final_step": 5,
            "fitness": 3.2,
            "classification": "unclassified",
            "summary": "Steady evolution toward complexity",
        },
        {
            "trajectory_id": 1,
            "final_step": 5,
            "fitness": 1.1,
            "classification": "unclassified",
            "summary": "Stagnation after initial progress",
        },
        {
            "trajectory_id": 2,
            "final_step": 5,
            "fitness": 7.5,
            "classification": "unclassified",
            "summary": "Rapid advancement driven by wildcard event",
        },
    ]


def test_resampling_critic_prompt_contains_state():
    prompt = build_resampling_critic_prompt(
        _sample_state(), "Life evolved.", _sample_summaries(),
    )
    assert "multicellular" in prompt
    assert "photosynthesis" in prompt
    assert "oxygen" in prompt


def test_resampling_critic_prompt_contains_narrative():
    prompt = build_resampling_critic_prompt(
        _sample_state(), "Life evolved significantly.", _sample_summaries(),
    )
    assert "Life evolved significantly." in prompt


def test_resampling_critic_prompt_contains_trajectory_summaries():
    summaries = _sample_summaries()
    prompt = build_resampling_critic_prompt(_sample_state(), "Narrative.", summaries)
    assert "trajectory_id" in prompt
    assert "Steady evolution" in prompt
    assert "Stagnation" in prompt
    assert "Rapid advancement" in prompt


def test_resampling_critic_prompt_requests_json_output():
    prompt = build_resampling_critic_prompt(
        _sample_state(), "Narrative.", _sample_summaries(),
    )
    assert '"scores"' in prompt
    assert '"trajectory_id"' in prompt
    assert '"score"' in prompt
    assert '"reasoning"' in prompt


def test_resampling_critic_prompt_mentions_evaluation_criteria():
    prompt = build_resampling_critic_prompt(
        _sample_state(), "Narrative.", _sample_summaries(),
    )
    assert "Plausibility" in prompt
    assert "Diversity" in prompt
    assert "Promise" in prompt


def test_resampling_critic_prompt_handles_empty_summaries():
    prompt = build_resampling_critic_prompt(_sample_state(), "Narrative.", [])
    assert "resampling critic" in prompt
    assert "[]" in prompt


def test_resampling_critic_prompt_handles_empty_state():
    prompt = build_resampling_critic_prompt({}, "Narrative.", _sample_summaries())
    assert "resampling critic" in prompt
    assert "{}" in prompt


def test_resampling_critic_role_exists():
    assert AgentRole.RESAMPLING_CRITIC == "resampling_critic"


def test_resampling_critic_in_agent_config():
    agent = AgentConfig(
        role=AgentRole.RESAMPLING_CRITIC,
        name="resampler",
        perspective="Evaluate trajectory fitness",
    )
    assert agent.role == AgentRole.RESAMPLING_CRITIC
    assert agent.name == "resampler"


def test_build_prompt_raises_for_resampling_critic():
    from minimal_agora.agents import build_prompt

    agent = AgentConfig(
        role=AgentRole.RESAMPLING_CRITIC,
        name="resampler",
        perspective="Evaluate trajectories",
    )
    try:
        build_prompt(agent, step=0)
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "build_resampling_critic_prompt" in str(e)


def test_resampling_critic_prompt_is_string():
    result = build_resampling_critic_prompt(
        _sample_state(), "Narrative.", _sample_summaries(),
    )
    assert isinstance(result, str)
    assert len(result) > 100
