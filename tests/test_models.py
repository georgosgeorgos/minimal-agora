import json
import tempfile
from pathlib import Path

from worldsim.analysis import aggregate_outcomes, format_report
from worldsim.board import Board, _deep_merge
from worldsim.models import (
    AgentConfig,
    AgentRole,
    AggregateResult,
    EntityConfig,
    InteractionConfig,
    InteractionMode,
    Proposal,
    Resolution,
    Scenario,
    SimMode,
    Step,
    Trajectory,
    TrajectoryOutcome,
    TrajectoryType,
    WildcardEvent,
)
from worldsim.scenario import load_scenario, setup_workspace

EXAMPLES_DIR = Path(__file__).parent.parent / "scenarios" / "examples"


def test_load_intelligence_scenario():
    scenario = load_scenario(EXAMPLES_DIR / "intelligence.yaml")
    assert scenario.name == "emergence-of-intelligence"
    assert scenario.mode == SimMode.COUNTERFACTUAL
    assert scenario.n_trajectories == 5
    assert len(scenario.agents) == 4
    assert scenario.agents[0].role == AgentRole.ACTOR
    assert scenario.agents[2].role == AgentRole.CRITIC
    assert scenario.agents[3].role == AgentRole.JUDGE


def test_setup_workspace():
    scenario = load_scenario(EXAMPLES_DIR / "intelligence.yaml")
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = setup_workspace(scenario, Path(tmpdir), trajectory_id=0)
        assert (workspace / "board" / "state.json").exists()
        assert (workspace / "board" / "scenario.md").exists()
        assert (workspace / "board" / "narrative.md").exists()
        assert (workspace / "history" / "step_000_state.json").exists()
        assert (workspace / "proposals").is_dir()
        assert (workspace / "critiques").is_dir()
        assert (workspace / "resolutions").is_dir()

        with open(workspace / "board" / "state.json") as f:
            state = json.load(f)
        assert state["life"]["complexity"] == "unicellular"


def test_deep_merge():
    base = {"a": 1, "b": {"c": 2, "d": 3}, "e": 4}
    overlay = {"b": {"c": 99, "f": 5}, "g": 6}
    _deep_merge(base, overlay)
    assert base == {"a": 1, "b": {"c": 99, "d": 3, "f": 5}, "e": 4, "g": 6}


def test_board_apply_resolution():
    scenario = load_scenario(EXAMPLES_DIR / "intelligence.yaml")
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = setup_workspace(scenario, Path(tmpdir), trajectory_id=0)
        board = Board(workspace)

        state_before = board.read_state()
        assert state_before["life"]["photosynthesis"] is False

        resolution = Resolution(
            state_delta={"life": {"photosynthesis": True}},
            narrative="Cyanobacteria evolved photosynthesis.",
            reasoning="Standard evolutionary timeline.",
        )

        state_after = board.apply_resolution(resolution, step=0)
        assert state_after["life"]["photosynthesis"] is True
        assert (workspace / "history" / "step_001_state.json").exists()


def test_aggregate_outcomes():
    trajectories = [
        Trajectory(
            scenario_name="test",
            trajectory_id=i,
            outcome=TrajectoryOutcome(
                classification="A" if i < 3 else "B",
                final_step=10,
                final_state={},
            ),
        )
        for i in range(5)
    ]
    result = aggregate_outcomes(trajectories, "test question")
    assert result.n_trajectories == 5
    assert result.outcomes["A"] == 3
    assert result.outcomes["B"] == 2
    assert abs(result.outcome_rates["A"] - 0.6) < 0.01


def test_format_report():
    result = AggregateResult(
        scenario_name="test",
        question="Did X happen?",
        n_trajectories=10,
        outcomes={"yes": 7, "no": 3},
        outcome_rates={"yes": 0.7, "no": 0.3},
        mean_steps_per_outcome={"yes": 5.0, "no": 8.0},
    )
    report = format_report(result)
    assert "test" in report
    assert "70.0%" in report
    assert "30.0%" in report


def test_load_mediterranean_scenario():
    scenario = load_scenario(EXAMPLES_DIR / "mediterranean.yaml")
    assert scenario.name == "mediterranean-powers"
    assert scenario.mode == SimMode.POPULATION
    assert len(scenario.entities) == 7
    populations = [e for e in scenario.entities if e.type.value == "population"]
    forces = [e for e in scenario.entities if e.type.value == "force"]
    critics = [e for e in scenario.entities if e.type.value == "critic"]
    evaluators = [e for e in scenario.entities if e.type.value == "evaluator"]
    assert len(populations) == 3
    assert len(forces) == 2
    assert len(critics) == 1
    assert len(evaluators) == 1


def test_entity_state_merged_into_workspace():
    scenario = load_scenario(EXAMPLES_DIR / "mediterranean.yaml")
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = setup_workspace(scenario, Path(tmpdir), trajectory_id=0)
        with open(workspace / "board" / "state.json") as f:
            state = json.load(f)
        assert "populations" in state
        assert "rome" in state["populations"]
        assert state["populations"]["rome"]["government"] == "republic"
        assert state["populations"]["greece"]["government"] == "city_states"
        assert state["populations"]["persia"]["government"] == "empire"
        assert state["world"]["era"] == "classical_antiquity"


def test_rules_loaded():
    scenario = load_scenario(EXAMPLES_DIR / "intelligence.yaml")
    assert len(scenario.rules) == 5
    names = [r.name for r in scenario.rules]
    assert "natural_selection" in names
    assert "complexity_ratchet" in names
    assert "extinction_as_opportunity" in names


def test_rules_in_prompt():
    from worldsim.agents import build_actor_prompt
    from worldsim.models import SimRule

    agent = AgentConfig(role=AgentRole.ACTOR, name="test", perspective="test perspective")
    rules = [
        SimRule(name="maximize_complexity", description="Evolve toward complexity"),
        SimRule(name="actor_only", description="Only for actors", applies_to=["actor"]),
        SimRule(name="critic_only", description="Only for critics", applies_to=["critic"]),
    ]
    prompt = build_actor_prompt(agent, step=0, rules=rules)
    assert "maximize_complexity" in prompt
    assert "actor_only" in prompt
    assert "critic_only" not in prompt


def test_fallback_resolution_deep_merges():
    from worldsim.loop import _fallback_resolution

    p1 = Proposal(
        agent="agent_a", role=AgentRole.ACTOR,
        proposed_changes={"life": {"complexity": "multicellular", "photosynthesis": True}},
        reasoning="evolution",
    )
    p2 = Proposal(
        agent="agent_b", role=AgentRole.ACTOR,
        proposed_changes={"life": {"nervous_system": True}, "environment": {"oxygen": "high"}},
        reasoning="geology",
    )
    resolution = _fallback_resolution([p1, p2])
    assert resolution.state_delta["life"]["complexity"] == "multicellular"
    assert resolution.state_delta["life"]["photosynthesis"] is True
    assert resolution.state_delta["life"]["nervous_system"] is True
    assert resolution.state_delta["environment"]["oxygen"] == "high"


def test_wildcards_loaded():
    scenario = load_scenario(EXAMPLES_DIR / "intelligence.yaml")
    assert len(scenario.wildcards) == 6
    names = [w.name for w in scenario.wildcards]
    assert "asteroid_impact" in names
    assert "gamma_ray_burst" in names
    assert "alien_contact" in names
    assert "deus_ex_machina" in names
    asteroid = next(w for w in scenario.wildcards if w.name == "asteroid_impact")
    assert asteroid.probability == 0.1
    assert "mass_extinctions" in asteroid.state_impact.get("environment", {})


def test_wildcard_board_write():
    scenario = load_scenario(EXAMPLES_DIR / "intelligence.yaml")
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = setup_workspace(scenario, Path(tmpdir), trajectory_id=0)
        board = Board(workspace)
        event = scenario.wildcards[0]
        path = board.write_wildcard(event, step=2)
        assert path.exists()
        with open(path) as f:
            data = json.load(f)
        assert data["name"] == event.name
        board.clear_wildcard(step=2)
        assert not path.exists()


def test_roll_wildcard():
    import random

    from worldsim.loop import _roll_wildcard

    events = [WildcardEvent(name="test", probability=1.0)]
    random.seed(42)
    assert _roll_wildcard(events) is not None

    events = [WildcardEvent(name="test", probability=0.0)]
    assert _roll_wildcard(events) is None


def test_wildcard_state_impact_applied():
    from worldsim.board import _deep_merge

    scenario = load_scenario(EXAMPLES_DIR / "intelligence.yaml")
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = setup_workspace(scenario, Path(tmpdir), trajectory_id=0)
        board = Board(workspace)
        state = board.read_state()
        assert state["environment"]["biodiversity"] == "low"
        asteroid = next(w for w in scenario.wildcards if w.name == "asteroid_impact")
        board.write_wildcard(asteroid, step=0)
        _deep_merge(state, asteroid.state_impact)
        board.write_state(state)
        updated = board.read_state()
        assert updated["environment"]["biodiversity"] == "collapse"
        assert updated["environment"]["mass_extinctions"] == "+1"


def test_proposal_roundtrip():
    p = Proposal(
        agent="test_agent",
        role=AgentRole.ACTOR,
        proposed_changes={"life": {"complexity": "multicellular"}},
        reasoning="Time for multicellularity",
        confidence=0.8,
    )
    data = p.model_dump_json()
    p2 = Proposal.model_validate_json(data)
    assert p2.agent == "test_agent"
    assert p2.proposed_changes["life"]["complexity"] == "multicellular"


def _make_entities():
    rome = EntityConfig(
        name="rome", type=TrajectoryType.POPULATION,
        state_prefix="populations.rome",
        agents=[AgentConfig(role=AgentRole.ACTOR, name="roman_senate", perspective="Rome")],
        can_interact_with=["greece"],
        interaction=InteractionConfig(mode=InteractionMode.ALWAYS),
    )
    greece = EntityConfig(
        name="greece", type=TrajectoryType.POPULATION,
        state_prefix="populations.greece",
        agents=[AgentConfig(role=AgentRole.ACTOR, name="greek_council", perspective="Greece")],
        can_interact_with=["rome"],
        interaction=InteractionConfig(mode=InteractionMode.ALWAYS),
    )
    persia = EntityConfig(
        name="persia", type=TrajectoryType.POPULATION,
        state_prefix="populations.persia",
        agents=[AgentConfig(role=AgentRole.ACTOR, name="persian_court", perspective="Persia")],
        can_interact_with=[],
        interaction=InteractionConfig(mode=InteractionMode.NEVER),
    )
    return [rome, greece, persia]


def _sample_state():
    return {
        "populations": {
            "rome": {"military_strength": 60, "economy": 50},
            "greece": {"military_strength": 45, "economy": 55},
            "persia": {"military_strength": 70, "economy": 65},
        },
    }


def test_interaction_context_always():
    from worldsim.agents import build_interaction_context

    entities = _make_entities()
    rome = entities[0]
    ctx = build_interaction_context(rome, entities, _sample_state(), step=0)
    assert "Greece" in ctx
    assert "military_strength" in ctx
    assert "45" in ctx
    assert "Persia" not in ctx


def test_interaction_context_never():
    from worldsim.agents import build_interaction_context

    entities = _make_entities()
    persia = entities[2]
    ctx = build_interaction_context(persia, entities, _sample_state(), step=0)
    assert ctx == ""


def test_interaction_context_scheduled():
    from worldsim.agents import build_interaction_context

    entities = _make_entities()
    rome = entities[0]
    rome.interaction = InteractionConfig(mode=InteractionMode.SCHEDULED, every_n_steps=3)
    ctx_step0 = build_interaction_context(rome, entities, _sample_state(), step=0)
    assert "Greece" in ctx_step0
    ctx_step1 = build_interaction_context(rome, entities, _sample_state(), step=1)
    assert ctx_step1 == ""
    ctx_step3 = build_interaction_context(rome, entities, _sample_state(), step=3)
    assert "Greece" in ctx_step3


def test_interaction_context_in_prompt():
    from worldsim.agents import build_actor_prompt, build_interaction_context

    entities = _make_entities()
    rome = entities[0]
    ctx = build_interaction_context(rome, entities, _sample_state(), step=0)
    agent = rome.agents[0]
    prompt = build_actor_prompt(agent, step=0, interaction_context=ctx)
    assert "Neighboring Populations" in prompt
    assert "Greece" in prompt
    assert "military_strength" in prompt


def test_can_interact_with_filters():
    from worldsim.agents import build_interaction_context

    entities = _make_entities()
    rome = entities[0]
    rome.can_interact_with = ["persia"]
    ctx = build_interaction_context(rome, entities, _sample_state(), step=0)
    assert "Persia" in ctx
    assert "Greece" not in ctx


def test_load_complexity_scenario():
    scenario = load_scenario(EXAMPLES_DIR / "complexity.yaml")
    assert scenario.name == "complexity-maximizer"
    assert scenario.mode == SimMode.OPEN_ENDED
    assert scenario.fitness is not None
    assert scenario.fitness.metric == "life.complexity"
    assert scenario.fitness.direction == "maximize"
    assert len(scenario.agents) == 4


def test_evaluate_fitness():
    from worldsim.loop import _evaluate_fitness
    from worldsim.models import FitnessConfig

    fitness = FitnessConfig(metric="life.complexity", direction="maximize")
    assert _evaluate_fitness({"life": {"complexity": 10.0}}, fitness) == 10.0
    assert _evaluate_fitness({"life": {"complexity": 42}}, fitness) == 42.0
    assert _evaluate_fitness({"life": {"complexity": "bacterial"}}, fitness) is None
    assert _evaluate_fitness({"other": {}}, fitness) is None


def test_check_plateau():
    from worldsim.loop import _check_plateau

    assert _check_plateau([1.0, 1.0, 1.0, 1.0, 1.0], window=5, threshold=0.01) is True
    assert _check_plateau([1.0, 2.0, 3.0, 4.0, 5.0], window=5, threshold=0.01) is False
    assert _check_plateau([1.0, 1.0, 1.0], window=5, threshold=0.01) is False
    assert _check_plateau([5.0, 5.001, 5.002, 5.001, 5.003], window=5, threshold=0.01) is True
    assert _check_plateau([None, None, 5.0, 5.0, 5.0, 5.0, 5.0], window=5, threshold=0.01) is True


def test_fitness_recorded_in_metadata():
    from worldsim.loop import _evaluate_fitness
    from worldsim.models import FitnessConfig

    fitness = FitnessConfig(metric="life.complexity")
    states = [
        {"life": {"complexity": 1.0}},
        {"life": {"complexity": 5.0}},
        {"life": {"complexity": 10.0}},
    ]
    history = [_evaluate_fitness(s, fitness) for s in states]
    t = Trajectory(
        scenario_name="test",
        trajectory_id=0,
        metadata={"fitness_history": history},
    )
    assert t.metadata["fitness_history"] == [1.0, 5.0, 10.0]


def test_diversity_prompt_varies_by_trajectory():
    from worldsim.agents import build_actor_prompt

    agent = AgentConfig(role=AgentRole.ACTOR, name="test", perspective="test")
    p0 = build_actor_prompt(agent, step=0, trajectory_id=0)
    p1 = build_actor_prompt(agent, step=0, trajectory_id=1)
    p5 = build_actor_prompt(agent, step=0, trajectory_id=5)
    assert "trajectory 0" in p0
    assert "trajectory 1" in p1
    assert "trajectory 5" in p5
    assert "most probable" in p0
    assert "unlikely but plausible" in p1
    assert "competition and conflict" in p5


def test_diversity_prompt_absent_without_trajectory_id():
    from worldsim.agents import build_actor_prompt

    agent = AgentConfig(role=AgentRole.ACTOR, name="test", perspective="test")
    p = build_actor_prompt(agent, step=0)
    assert "Exploration lens" not in p


def test_resume_detection_empty():
    from worldsim.loop import _detect_resume_point

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        assert _detect_resume_point(workspace) == 0


def test_resume_detection_with_history():
    from worldsim.loop import _detect_resume_point

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        history = workspace / "history"
        history.mkdir()
        for i in range(3):
            step = Step(step_number=i, state_before={}, state_after={"x": i})
            with open(history / f"step_{i:03d}_full.json", "w") as f:
                f.write(step.model_dump_json())
        assert _detect_resume_point(workspace) == 3


def test_skip_completed_trajectory():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        (workspace / "board").mkdir(parents=True)
        (workspace / "history").mkdir()
        (workspace / "proposals").mkdir()
        (workspace / "critiques").mkdir()
        (workspace / "resolutions").mkdir()
        with open(workspace / "board" / "state.json", "w") as f:
            json.dump({"x": 1}, f)

        t = Trajectory(
            scenario_name="test", trajectory_id=0,
            steps=[Step(step_number=0, state_before={}, state_after={"x": 1})],
            outcome=TrajectoryOutcome(classification="done", final_step=0, final_state={"x": 1}),
        )
        with open(workspace / "trajectory.json", "w") as f:
            f.write(t.model_dump_json())

        import asyncio

        from worldsim.loop import run_trajectory

        scenario = Scenario(
            name="test", mode=SimMode.COUNTERFACTUAL,
            initial_state={"x": 0}, step_budget=5,
            termination={"max_steps": 5},
        )
        result = asyncio.run(run_trajectory(scenario, workspace, 0))
        assert result.outcome is not None
        assert result.outcome.classification == "done"


def test_load_pandemic_scenario():
    scenario = load_scenario(EXAMPLES_DIR / "pandemic.yaml")
    assert scenario.name == "pandemic-spread"
    assert scenario.mode == SimMode.COUNTERFACTUAL
    assert scenario.n_trajectories == 10
    assert len(scenario.agents) == 5
    assert len(scenario.rules) == 4
    assert len(scenario.wildcards) == 3
    assert scenario.initial_state["disease"]["transmissibility"] == 0.7
    assert "east_asia" in scenario.initial_state["regions"]


def test_load_market_scenario():
    scenario = load_scenario(EXAMPLES_DIR / "market.yaml")
    assert scenario.name == "market-competition"
    assert scenario.mode == SimMode.POPULATION
    assert len(scenario.entities) == 7
    populations = [e for e in scenario.entities if e.type.value == "population"]
    assert len(populations) == 3
    assert populations[0].can_interact_with == ["beta_inc", "gamma_labs"]
    assert len(scenario.rules) == 4
    cap_rule = next(r for r in scenario.rules if r.name == "capitalistic_incentives")
    assert "population" in cap_rule.applies_to


def test_convergence_detection():
    from worldsim.analysis import detect_convergence

    converged = [
        Trajectory(
            scenario_name="test", trajectory_id=i,
            outcome=TrajectoryOutcome(classification="same", final_step=10, final_state={}),
        )
        for i in range(10)
    ]
    warnings = detect_convergence(converged)
    assert len(warnings) == 1
    assert "mode collapse" in warnings[0].lower()

    diverse = [
        Trajectory(
            scenario_name="test", trajectory_id=i,
            outcome=TrajectoryOutcome(
                classification=["A", "B", "C", "D"][i % 4], final_step=10, final_state={},
            ),
        )
        for i in range(12)
    ]
    assert detect_convergence(diverse) == []
