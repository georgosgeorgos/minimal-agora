import json
import tempfile
from pathlib import Path

from minimal_agora.agents import build_resampling_critic_prompt, parse_resampling_score
from minimal_agora.models import (
    DEFAULT_RESAMPLING_CRITERIA,
    ResamplingConfig,
    ResamplingScore,
    Scenario,
    SimMode,
)
from minimal_agora.resampling import compute_weights, fork_workspace, systematic_resample


def test_resampling_config_default():
    cfg = ResamplingConfig()
    assert cfg.interval == 5
    assert cfg.criteria == []
    assert cfg.min_particles == 2


def test_scenario_resampling_none_by_default():
    scenario = Scenario(
        name="test", mode=SimMode.COUNTERFACTUAL,
        initial_state={"x": 0}, step_budget=5,
    )
    assert scenario.resampling is None


def test_scenario_with_resampling():
    scenario = Scenario(
        name="test", mode=SimMode.COUNTERFACTUAL,
        initial_state={"x": 0}, step_budget=5,
        resampling=ResamplingConfig(interval=3, criteria=["Is it good?"]),
    )
    assert scenario.resampling is not None
    assert scenario.resampling.interval == 3
    assert scenario.resampling.criteria == ["Is it good?"]


def test_systematic_resample():
    weights = [0.5, 0.3, 0.1, 0.1]
    indices = systematic_resample(weights, 4)
    assert len(indices) == 4
    assert all(0 <= i < 4 for i in indices)
    assert indices.count(0) >= indices.count(3)


def test_compute_weights_laplace():
    scores = [
        ResamplingScore(trajectory_id=0, scores=[0, 0, 0], total=0),
        ResamplingScore(trajectory_id=1, scores=[0, 0, 0], total=0),
        ResamplingScore(trajectory_id=2, scores=[0, 0, 0], total=0),
    ]
    weights = compute_weights(scores)
    assert len(weights) == 3
    assert all(w > 0 for w in weights)
    assert abs(sum(weights) - 1.0) < 1e-9
    assert all(abs(w - 1 / 3) < 1e-9 for w in weights)


def test_compute_weights_normal():
    scores = [
        ResamplingScore(trajectory_id=0, scores=[1] * 10, total=10),
        ResamplingScore(trajectory_id=1, scores=[1] * 5, total=5),
        ResamplingScore(trajectory_id=2, scores=[], total=0),
    ]
    weights = compute_weights(scores)
    assert abs(sum(weights) - 1.0) < 1e-9
    assert abs(weights[0] - 11 / 18) < 1e-9
    assert abs(weights[1] - 6 / 18) < 1e-9
    assert abs(weights[2] - 1 / 18) < 1e-9


def test_fork_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "src_ws"
        dst = Path(tmpdir) / "dst_ws"
        src.mkdir()
        (src / "board").mkdir()
        (src / "board" / "state.json").write_text('{"x": 1}')
        (src / "narrative.md").write_text("# Log")

        fork_workspace(src, dst)

        assert dst.exists()
        assert (dst / "board" / "state.json").exists()
        assert json.loads((dst / "board" / "state.json").read_text()) == {"x": 1}
        assert (dst / "narrative.md").read_text() == "# Log"


def test_build_resampling_critic_prompt():
    criteria = ["Criterion A?", "Criterion B?", "Criterion C?"]
    prompt = build_resampling_critic_prompt(criteria, step=5)
    for c in criteria:
        assert c in prompt
    assert "step 5" in prompt
    assert "resample_step_005.json" in prompt
    assert "exactly 3 elements" in prompt


def test_default_criteria_used():
    cfg = ResamplingConfig()
    criteria = cfg.criteria or DEFAULT_RESAMPLING_CRITERIA
    assert len(criteria) == 10
    assert criteria is DEFAULT_RESAMPLING_CRITERIA


def test_parse_resampling_score():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        critiques = workspace / "critiques"
        critiques.mkdir()
        data = {"scores": [1, 0, 1, 1], "total": 3, "notes": "test"}
        (critiques / "resample_step_005.json").write_text(json.dumps(data))
        score = parse_resampling_score(workspace, step=5, trajectory_id=2)
        assert score is not None
        assert score.trajectory_id == 2
        assert score.scores == [1, 0, 1, 1]
        assert score.total == 3
        assert score.notes == "test"


def test_parse_resampling_score_missing():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        (workspace / "critiques").mkdir()
        score = parse_resampling_score(workspace, step=5, trajectory_id=0)
        assert score is None


def test_systematic_resample_uniform():
    weights = [0.25, 0.25, 0.25, 0.25]
    indices = systematic_resample(weights, 4)
    assert sorted(indices) == [0, 1, 2, 3]


def test_systematic_resample_degenerate():
    weights = [1.0, 0.0, 0.0]
    indices = systematic_resample(weights, 3)
    assert all(i == 0 for i in indices)
