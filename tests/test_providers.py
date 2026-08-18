import asyncio
import tempfile
from pathlib import Path

from minimal_agora.agents import get_default_provider, invoke_agent, set_default_provider
from minimal_agora.models import AgentConfig, AgentRole
from minimal_agora.providers import (
    AgentInvocationResult,
    AgentProvider,
    ClaudeSubprocessProvider,
    MockProvider,
)


def _make_agent(name: str = "test_agent", role: AgentRole = AgentRole.ACTOR) -> AgentConfig:
    return AgentConfig(role=role, name=name, perspective="test perspective")


class TestAgentInvocationResult:
    def test_defaults(self) -> None:
        result = AgentInvocationResult(output="hello")
        assert result.output == "hello"
        assert result.tokens_used is None
        assert result.model is None

    def test_with_metadata(self) -> None:
        result = AgentInvocationResult(output="hi", tokens_used=42, model="test-model")
        assert result.tokens_used == 42
        assert result.model == "test-model"


class TestMockProvider:
    def test_returns_default_response(self) -> None:
        provider = MockProvider()
        with tempfile.TemporaryDirectory() as tmp:
            result = asyncio.run(provider.invoke("anything", Path(tmp)))
        assert result.output == "Mock response"
        assert result.tokens_used == 100
        assert result.model == "mock-model"

    def test_returns_keyed_response(self) -> None:
        provider = MockProvider(responses={"actor": "actor proposal"})
        with tempfile.TemporaryDirectory() as tmp:
            result = asyncio.run(provider.invoke("You are an actor agent", Path(tmp)))
        assert result.output == "actor proposal"

    def test_tracks_call_count(self) -> None:
        provider = MockProvider()
        with tempfile.TemporaryDirectory() as tmp:
            asyncio.run(provider.invoke("a", Path(tmp)))
            asyncio.run(provider.invoke("b", Path(tmp)))
        assert provider.call_count == 2

    def test_records_last_prompt(self) -> None:
        provider = MockProvider()
        with tempfile.TemporaryDirectory() as tmp:
            asyncio.run(provider.invoke("hello world", Path(tmp)))
        assert provider.last_prompt == "hello world"

    def test_satisfies_protocol(self) -> None:
        assert isinstance(MockProvider(), AgentProvider)


class TestClaudeSubprocessProvider:
    def test_build_command_defaults(self) -> None:
        provider = ClaudeSubprocessProvider()
        cmd = provider.build_command("test prompt", Path("/tmp/workspace"))
        assert cmd == [
            "claude",
            "-p",
            "test prompt",
            "--output-format",
            "text",
            "--max-turns",
            "5",
            "--allowedTools",
            "Read,Write,Bash",
            "--add-dir",
            "/tmp/workspace",
        ]

    def test_build_command_custom(self) -> None:
        provider = ClaudeSubprocessProvider(max_turns=10, output_format="json")
        cmd = provider.build_command("hello", Path("/tmp/ws"))
        assert "--max-turns" in cmd
        assert cmd[cmd.index("--max-turns") + 1] == "10"
        assert "--output-format" in cmd
        assert cmd[cmd.index("--output-format") + 1] == "json"

    def test_build_command_includes_tool_permissions(self) -> None:
        provider = ClaudeSubprocessProvider()
        workspace = Path("/tmp/test-workspace")
        cmd = provider.build_command("prompt", workspace)
        assert "--allowedTools" in cmd
        assert cmd[cmd.index("--allowedTools") + 1] == "Read,Write,Bash"
        assert "--add-dir" in cmd
        assert cmd[cmd.index("--add-dir") + 1] == str(workspace)

    def test_satisfies_protocol(self) -> None:
        assert isinstance(ClaudeSubprocessProvider(), AgentProvider)


class TestSetDefaultProvider:
    def test_set_and_get_default_provider(self) -> None:
        original = get_default_provider()
        try:
            mock = MockProvider()
            set_default_provider(mock)
            assert get_default_provider() is mock
        finally:
            set_default_provider(original)

    def test_invoke_agent_uses_default_provider(self) -> None:
        original = get_default_provider()
        try:
            mock = MockProvider(responses={"actor": "mock output"})
            set_default_provider(mock)
            agent = _make_agent()
            with tempfile.TemporaryDirectory() as tmp:
                result = asyncio.run(invoke_agent(agent, Path(tmp), step=1, prompt="actor test"))
            assert result == "mock output"
            assert mock.call_count == 1
        finally:
            set_default_provider(original)

    def test_invoke_agent_uses_explicit_provider(self) -> None:
        explicit = MockProvider(responses={"critic": "explicit output"})
        agent = _make_agent(role=AgentRole.CRITIC)
        with tempfile.TemporaryDirectory() as tmp:
            result = asyncio.run(
                invoke_agent(agent, Path(tmp), step=1, prompt="critic test", provider=explicit)
            )
        assert result == "explicit output"
        assert explicit.call_count == 1


class TestTopLevelExports:
    def test_provider_exports(self) -> None:
        import minimal_agora

        assert hasattr(minimal_agora, "AgentProvider")
        assert hasattr(minimal_agora, "AgentInvocationResult")
        assert hasattr(minimal_agora, "ClaudeSubprocessProvider")
        assert hasattr(minimal_agora, "MockProvider")
        assert hasattr(minimal_agora, "set_default_provider")

    def test_all_contains_provider_names(self) -> None:
        import minimal_agora

        expected = {
            "AgentProvider",
            "AgentInvocationResult",
            "ClaudeSubprocessProvider",
            "MockProvider",
            "set_default_provider",
        }
        assert expected.issubset(set(minimal_agora.__all__))
