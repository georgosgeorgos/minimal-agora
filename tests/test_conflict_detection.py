from __future__ import annotations

from minimal_agora.agents import _format_conflicts, detect_conflicts
from minimal_agora.models import AgentRole, Conflict, ConflictSource, Proposal


def _make_proposal(agent: str, changes: dict) -> Proposal:
    return Proposal(agent=agent, role=AgentRole.ACTOR, proposed_changes=changes)


def test_no_conflicts_different_fields():
    proposals = [
        _make_proposal("agent_a", {"population": 100}),
        _make_proposal("agent_b", {"climate": "warm"}),
    ]
    conflicts = detect_conflicts(proposals)
    assert conflicts == []


def test_single_conflict_same_field():
    proposals = [
        _make_proposal("agent_a", {"population": 100}),
        _make_proposal("agent_b", {"population": 200}),
    ]
    conflicts = detect_conflicts(proposals)
    assert len(conflicts) == 1
    assert conflicts[0].field == "population"
    assert len(conflicts[0].sources) == 2
    names = {s.agent_name for s in conflicts[0].sources}
    assert names == {"agent_a", "agent_b"}


def test_multi_field_conflicts():
    proposals = [
        _make_proposal("agent_a", {"population": 100, "climate": "warm"}),
        _make_proposal("agent_b", {"population": 200, "climate": "cold"}),
        _make_proposal("agent_c", {"economy": "growing"}),
    ]
    conflicts = detect_conflicts(proposals)
    conflict_fields = {c.field for c in conflicts}
    assert conflict_fields == {"population", "climate"}
    for c in conflicts:
        if c.field in ("population", "climate"):
            assert len(c.sources) == 2


def test_empty_proposals():
    conflicts = detect_conflicts([])
    assert conflicts == []


def test_nested_key_conflict():
    proposals = [
        _make_proposal("agent_a", {"planet": {"temperature": 15}}),
        _make_proposal("agent_b", {"planet": {"temperature": 20}}),
    ]
    conflicts = detect_conflicts(proposals)
    assert len(conflicts) == 1
    assert conflicts[0].field == "planet.temperature"


def test_three_way_conflict():
    proposals = [
        _make_proposal("a", {"size": 10}),
        _make_proposal("b", {"size": 20}),
        _make_proposal("c", {"size": 30}),
    ]
    conflicts = detect_conflicts(proposals)
    assert len(conflicts) == 1
    assert len(conflicts[0].sources) == 3


def test_format_conflicts_output():
    conflicts = [
        Conflict(
            field="population.size",
            sources=[
                ConflictSource(agent_name="natural_selection", proposed_value=1200),
                ConflictSource(agent_name="environmental_change", proposed_value=800),
            ],
        ),
    ]
    text = _format_conflicts(conflicts)
    assert "## Conflicts Requiring Resolution" in text
    assert "population.size" in text
    assert "natural_selection" in text
    assert "environmental_change" in text
    assert "You MUST explicitly resolve each conflict above." in text


def test_conflict_model_validation():
    c = Conflict(
        field="test_field",
        sources=[
            ConflictSource(agent_name="a", proposed_value=1),
            ConflictSource(agent_name="b", proposed_value=2),
        ],
    )
    assert c.field == "test_field"
    assert len(c.sources) == 2
    assert c.sources[0].agent_name == "a"
    assert c.sources[0].proposed_value == 1
