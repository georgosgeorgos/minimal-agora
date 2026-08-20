import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

EXAMPLES_DIR = Path(__file__).parent.parent / "scenarios" / "examples"


def test_public_api_imports():
    import minimal_agora

    assert hasattr(minimal_agora, "run_trajectory")
    assert hasattr(minimal_agora, "run_batch")
    assert hasattr(minimal_agora, "load_scenario")
    assert hasattr(minimal_agora, "Scenario")
    assert hasattr(minimal_agora, "Trajectory")
    assert hasattr(minimal_agora, "AgentConfig")
    assert hasattr(minimal_agora, "EntityConfig")


def test_public_api_all():
    import minimal_agora

    assert "run_trajectory" in minimal_agora.__all__
    assert "run_batch" in minimal_agora.__all__
    assert "load_scenario" in minimal_agora.__all__
    assert "Scenario" in minimal_agora.__all__
    assert "Trajectory" in minimal_agora.__all__
    assert "AgentConfig" in minimal_agora.__all__
    assert "EntityConfig" in minimal_agora.__all__


def test_public_api_load_scenario():
    import minimal_agora

    scenario = minimal_agora.load_scenario(EXAMPLES_DIR / "intelligence.yaml")
    assert isinstance(scenario, minimal_agora.Scenario)
    assert scenario.name == "emergence-of-intelligence"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "minimal_agora.cli", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_validate_valid_scenario():
    result = _run_cli("validate", str(EXAMPLES_DIR / "intelligence.yaml"))
    assert result.returncode == 0
    assert "Valid" in result.stdout


def test_validate_invalid_scenario():
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        yaml.dump({"name": "bad", "missing_mode": True}, f)
        f.flush()
        result = _run_cli("validate", f.name)
    assert result.returncode == 1
    assert "Invalid" in result.stdout


def test_init_scenario_creates_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            [sys.executable, "-m", "minimal_agora.cli", "init-scenario", "my-test", "--mode", "counterfactual"],
            capture_output=True,
            text=True,
            cwd=tmpdir,
            check=False,
        )
        assert result.returncode == 0
        assert "Created scenario template" in result.stdout

        generated = Path(tmpdir) / "my-test.yaml"
        assert generated.exists()
        with open(generated) as f:
            data = yaml.safe_load(f)
        assert data["name"] == "my-test"
        assert data["mode"] == "counterfactual"
        assert "agents" in data


def test_init_scenario_population_mode():
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            [sys.executable, "-m", "minimal_agora.cli", "init-scenario", "pop-test", "--mode", "population"],
            capture_output=True,
            text=True,
            cwd=tmpdir,
            check=False,
        )
        assert result.returncode == 0
        generated = Path(tmpdir) / "pop-test.yaml"
        with open(generated) as f:
            data = yaml.safe_load(f)
        assert data["mode"] == "population"
        assert "entities" in data


def test_agents_flat_scenario():
    result = _run_cli("agents", str(EXAMPLES_DIR / "intelligence.yaml"))
    assert result.returncode == 0
    assert "natural_selection" in result.stdout
    assert "actor" in result.stdout
    assert "plausibility_critic" in result.stdout


def test_agents_population_scenario():
    result = _run_cli("agents", str(EXAMPLES_DIR / "mediterranean.yaml"))
    assert result.returncode == 0
    assert "Entities:" in result.stdout
    assert "population" in result.stdout


def test_version():
    result = _run_cli("version")
    assert result.returncode == 0
    assert "minimal-agora" in result.stdout


def test_dry_run():
    result = _run_cli("run", str(EXAMPLES_DIR / "intelligence.yaml"), "--dry-run")
    assert result.returncode == 0
    assert "Dry run complete" in result.stdout
    assert "emergence-of-intelligence" in result.stdout
    assert "counterfactual" in result.stdout


def test_dry_run_population():
    result = _run_cli("run", str(EXAMPLES_DIR / "mediterranean.yaml"), "--dry-run")
    assert result.returncode == 0
    assert "Dry run complete" in result.stdout
    assert "Entities:" in result.stdout


def test_validate_invalid_yaml_friendly_error():
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        yaml.dump({"name": "bad", "mode": "counterfactual"}, f)
        f.flush()
        result = _run_cli("validate", f.name)
    assert result.returncode == 1
    assert "Invalid scenario:" in result.stdout
    assert "initial_state" in result.stdout
    assert "Field required" in result.stdout


def test_init_scenario_no_overwrite():
    with tempfile.TemporaryDirectory() as tmpdir:
        existing = Path(tmpdir) / "existing.yaml"
        existing.write_text("placeholder")
        result = subprocess.run(
            [sys.executable, "-m", "minimal_agora.cli", "init-scenario", "existing"],
            capture_output=True,
            text=True,
            cwd=tmpdir,
            check=False,
        )
        assert result.returncode == 1
        assert "File already exists" in result.stdout
        assert "--force" in result.stdout
        assert existing.read_text() == "placeholder"


def test_init_scenario_force():
    with tempfile.TemporaryDirectory() as tmpdir:
        existing = Path(tmpdir) / "forced.yaml"
        existing.write_text("placeholder")
        result = subprocess.run(
            [sys.executable, "-m", "minimal_agora.cli", "init-scenario", "forced", "--force"],
            capture_output=True,
            text=True,
            cwd=tmpdir,
            check=False,
        )
        assert result.returncode == 0
        assert "Created scenario template" in result.stdout
        data = yaml.safe_load(existing.read_text())
        assert data["name"] == "forced"


def test_agents_missing_file():
    result = _run_cli("agents", "/tmp/nonexistent_scenario_xyz.yaml")
    assert result.returncode == 1
    assert "Scenario file not found" in result.stdout


def test_run_missing_scenario():
    result = _run_cli("run", "/tmp/nonexistent_scenario_xyz.yaml")
    assert result.returncode == 1
    assert "Scenario file not found" in result.stdout


def test_report_json_format():
    from minimal_agora.models import Trajectory, TrajectoryOutcome

    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / "run"
        traj_dir = run_dir / "trajectory_000"
        traj_dir.mkdir(parents=True)

        t = Trajectory(
            scenario_name="test",
            trajectory_id=0,
            outcome=TrajectoryOutcome(classification="A", final_step=5, final_state={}),
        )
        with open(traj_dir / "trajectory.json", "w") as f:
            f.write(t.model_dump_json())

        result = _run_cli("report", str(run_dir), "--format", "json")
        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        assert parsed["scenario_name"] == "test"
        assert parsed["n_trajectories"] == 1


def _run_namespace(**kwargs):
    """Build an argparse.Namespace matching the `run` subcommand's args."""
    from argparse import Namespace

    defaults = {
        "provider": None,
        "model": None,
        "api_base": None,
        "api_key": None,
    }
    defaults.update(kwargs)
    return Namespace(**defaults)


def test_create_provider_anthropic_passes_api_key_and_base():
    from minimal_agora.cli import _create_provider
    from minimal_agora.providers import AnthropicAPIProvider

    args = _run_namespace(
        provider="anthropic",
        model="claude-haiku-4-5-20251001",
        api_base="http://localhost:8080",
        api_key="sk-test",
    )
    provider = _create_provider(args)
    assert isinstance(provider, AnthropicAPIProvider)
    assert provider.model == "claude-haiku-4-5-20251001"
    assert provider.base_url == "http://localhost:8080"
    assert provider.api_key == "sk-test"


def test_create_provider_anthropic_defaults_to_none():
    """Without flags, api_key/base_url are None so the SDK reads env vars."""
    from minimal_agora.cli import _create_provider
    from minimal_agora.providers import AnthropicAPIProvider

    args = _run_namespace(provider="anthropic")
    provider = _create_provider(args)
    assert isinstance(provider, AnthropicAPIProvider)
    assert provider.api_key is None
    assert provider.base_url is None


def test_create_provider_litellm_passes_api_key_and_base():
    from minimal_agora.cli import _create_provider
    from minimal_agora.providers import LiteLLMProvider

    args = _run_namespace(
        provider="litellm",
        model="openai/gpt-4o",
        api_base="http://localhost:8000/v1",
        api_key="sk-test",
    )
    provider = _create_provider(args)
    assert isinstance(provider, LiteLLMProvider)
    assert provider.model == "openai/gpt-4o"
    assert provider.api_base == "http://localhost:8000/v1"
    assert provider.api_key == "sk-test"
