from minimal_agora.models import ResamplingConfig, Scenario, SimMode
from minimal_agora.resampling import effective_sample_size


def test_ess_uniform_weights():
    weights = [0.25, 0.25, 0.25, 0.25]
    ess = effective_sample_size(weights)
    assert abs(ess - 4.0) < 1e-9


def test_ess_single_weight():
    weights = [1.0, 0.0, 0.0, 0.0]
    ess = effective_sample_size(weights)
    assert abs(ess - 1.0) < 1e-9


def test_ess_two_equal():
    weights = [0.5, 0.5, 0.0, 0.0]
    ess = effective_sample_size(weights)
    assert abs(ess - 2.0) < 1e-9


def test_ess_known_distribution():
    weights = [0.4, 0.3, 0.2, 0.1]
    expected = 1.0 / (0.16 + 0.09 + 0.04 + 0.01)
    ess = effective_sample_size(weights)
    assert abs(ess - expected) < 1e-9


def test_ess_all_zero():
    weights = [0.0, 0.0, 0.0]
    ess = effective_sample_size(weights)
    assert ess == 0.0


def test_ess_threshold_triggers_resample():
    n = 10
    threshold = 0.5
    weights = [0.91, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01]
    ess = effective_sample_size(weights)
    assert ess < threshold * n


def test_ess_threshold_no_resample():
    n = 10
    threshold = 0.5
    weights = [0.1] * 10
    ess = effective_sample_size(weights)
    assert ess >= threshold * n


def test_ess_threshold_boundary():
    n = 4
    threshold = 0.5
    weights = [0.5, 0.5, 0.0, 0.0]
    ess = effective_sample_size(weights)
    assert ess == threshold * n


def test_resampling_config_ess_threshold_default():
    cfg = ResamplingConfig()
    assert cfg.ess_threshold == 0.5


def test_resampling_config_custom_ess_threshold():
    cfg = ResamplingConfig(ess_threshold=0.7)
    assert cfg.ess_threshold == 0.7


def test_resampling_config_ess_zero_disables():
    cfg = ResamplingConfig(ess_threshold=0.0)
    n = 4
    weights = [1.0, 0.0, 0.0, 0.0]
    ess = effective_sample_size(weights)
    assert ess >= cfg.ess_threshold * n


def test_resampling_config_ess_one_always():
    cfg = ResamplingConfig(ess_threshold=1.0)
    n = 4
    weights = [0.25, 0.25, 0.25, 0.25]
    ess = effective_sample_size(weights)
    assert ess <= cfg.ess_threshold * n


def test_scenario_with_ess_threshold():
    scenario = Scenario(
        name="test", mode=SimMode.COUNTERFACTUAL,
        initial_state={"x": 0}, step_budget=5,
        resampling=ResamplingConfig(ess_threshold=0.3),
    )
    assert scenario.resampling is not None
    assert scenario.resampling.ess_threshold == 0.3
