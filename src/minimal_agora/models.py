from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SimMode(str, Enum):
    COUNTERFACTUAL = "counterfactual"
    OPEN_ENDED = "open_ended"
    POPULATION = "population"


class AgentRole(str, Enum):
    ACTOR = "actor"
    CRITIC = "critic"
    JUDGE = "judge"


class AgentConfig(BaseModel):
    """Configuration for a single LLM agent within a simulation."""

    model_config = ConfigDict(extra="forbid")

    role: AgentRole
    name: str
    perspective: str
    model: str | None = None


class TerminationCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    equals: Any = None
    greater_than: float | None = None
    less_than: float | None = None


class OutcomeClass(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    condition: TerminationCondition | None = None
    default: bool = False


class OutcomeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    classifier: list[OutcomeClass]


class TrajectoryType(str, Enum):
    POPULATION = "population"
    FORCE = "force"
    CRITIC = "critic"
    EVALUATOR = "evaluator"


class InteractionMode(str, Enum):
    ALWAYS = "always"
    CONDITIONAL = "conditional"
    SCHEDULED = "scheduled"
    NEVER = "never"


class InteractionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: InteractionMode = InteractionMode.ALWAYS
    every_n_steps: int = 1
    conditions: list[dict[str, Any]] = Field(default_factory=list)


class EntityConfig(BaseModel):
    """Configuration for an entity (population, force, critic, or evaluator) in population mode."""

    model_config = ConfigDict(extra="forbid")

    name: str
    type: TrajectoryType
    state_prefix: str = ""
    initial_state: dict[str, Any] = Field(default_factory=dict)
    agents: list[AgentConfig] = Field(default_factory=list)
    can_interact_with: list[str] = Field(default_factory=list)
    interaction: InteractionConfig = Field(default_factory=InteractionConfig)


class SimRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    applies_to: list[str] = Field(default_factory=list)


class WildcardEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    probability: float = 0.1
    description: str = ""
    state_impact: dict[str, Any] = Field(default_factory=dict)


class FitnessConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    direction: str = "maximize"


class ResamplingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interval: int = Field(default=5, ge=1)
    criteria: list[str] = Field(default_factory=list)
    min_particles: int = Field(default=2, ge=1)


class ResamplingScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trajectory_id: int
    scores: list[int]
    total: int
    notes: str = ""


DEFAULT_RESAMPLING_CRITERIA = [
    "Did the system state change meaningfully this period?",
    "Did a novel entity, force, or dynamic emerge?",
    "Is there active conflict or tension between forces?",
    "Did complexity increase (new structures, relationships, or hierarchies)?",
    "Did an unexpected or surprising event occur?",
    "Are there unresolved tensions that could drive future change?",
    "Is this trajectory exploring a unique path compared to the initial state?",
    "Did the environment or external conditions change significantly?",
    "Are there second-order effects or cascading consequences unfolding?",
    "Would continuing this trajectory likely produce new information?",
]


class Scenario(BaseModel):
    """Top-level simulation scenario defining agents, rules, and termination conditions."""

    model_config = ConfigDict(extra="forbid")

    name: str
    mode: SimMode
    n_trajectories: int = 1
    step_budget: int = 50
    initial_state: dict[str, Any]
    agents: list[AgentConfig] = Field(default_factory=list)
    entities: list[EntityConfig] = Field(default_factory=list)
    termination: dict[str, Any] = Field(default_factory=dict)
    rules: list[SimRule] = Field(default_factory=list)
    outcome: OutcomeConfig | None = None
    fitness: FitnessConfig | None = None
    wildcards: list[WildcardEvent] = Field(default_factory=list)
    wildcards_enabled: bool = False
    description: str = ""
    max_concurrent_agents: int = Field(default=8, ge=1)
    review_interval: int = Field(default=1, ge=1)
    resampling: ResamplingConfig | None = None


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent: str
    role: AgentRole
    proposed_changes: dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""
    confidence: float = 0.5


class Critique(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent: str
    target_proposals: list[str] = Field(default_factory=list)
    assessment: str = ""
    plausibility: float = 0.5
    issues: list[str] = Field(default_factory=list)


class Resolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_delta: dict[str, Any] = Field(default_factory=dict)
    narrative: str = ""
    reasoning: str = ""


class Evaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity: str
    scores: dict[str, float] = Field(default_factory=dict)
    assessment: str = ""
    rewards: dict[str, float] = Field(default_factory=dict)


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_number: int
    proposals: list[Proposal] = Field(default_factory=list)
    critiques: list[Critique] = Field(default_factory=list)
    resolution: Resolution | None = None
    state_before: dict[str, Any] = Field(default_factory=dict)
    state_after: dict[str, Any] = Field(default_factory=dict)


class TrajectoryOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification: str
    final_step: int
    final_state: dict[str, Any] = Field(default_factory=dict)


class Trajectory(BaseModel):
    """Record of a single simulation run including steps and final outcome."""

    model_config = ConfigDict(extra="forbid")

    scenario_name: str
    trajectory_id: int
    steps: list[Step] = Field(default_factory=list)
    outcome: TrajectoryOutcome | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AggregateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_name: str
    question: str
    n_trajectories: int
    outcomes: dict[str, int] = Field(default_factory=dict)
    outcome_rates: dict[str, float] = Field(default_factory=dict)
    mean_steps_per_outcome: dict[str, float] = Field(default_factory=dict)
    outcome_rates_ci: dict[str, tuple[float, float]] | None = None
    monte_carlo_se: dict[str, float] | None = None


class CrossRunComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_a_name: str
    run_b_name: str
    n_trajectories_a: int
    n_trajectories_b: int
    outcome_comparisons: list[dict[str, Any]] = Field(default_factory=list)
    metric_comparisons: list[dict[str, Any]] = Field(default_factory=list)
    effect_sizes: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
