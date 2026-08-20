import os

import pytest


def test_load_env_noop_when_dotenv_missing(monkeypatch):
    """load_env must not raise if python-dotenv is unavailable."""
    from minimal_agora import env as env_module

    monkeypatch.setattr(env_module, "_HAS_DOTENV", False)
    # Should be a safe no-op.
    env_module.load_env()


def test_load_env_reads_env_file(monkeypatch, tmp_path):
    """A .env file in the cwd is loaded into os.environ."""
    pytest.importorskip("dotenv")
    from minimal_agora import env as env_module

    monkeypatch.setattr(env_module, "_HAS_DOTENV", True)

    env_file = tmp_path / ".env"
    env_file.write_text("MINIMAL_AGORA_TEST_KEY=from-dotenv\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MINIMAL_AGORA_TEST_KEY", raising=False)

    env_module.load_env()
    assert os.environ.get("MINIMAL_AGORA_TEST_KEY") == "from-dotenv"


def test_load_env_does_not_override_existing(monkeypatch, tmp_path):
    """Real env vars take precedence over .env values."""
    pytest.importorskip("dotenv")
    from minimal_agora import env as env_module

    monkeypatch.setattr(env_module, "_HAS_DOTENV", True)

    env_file = tmp_path / ".env"
    env_file.write_text("MINIMAL_AGORA_OVERRIDE=from-dotenv\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MINIMAL_AGORA_OVERRIDE", "from-real-env")

    env_module.load_env()
    assert os.environ["MINIMAL_AGORA_OVERRIDE"] == "from-real-env"
