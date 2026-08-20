import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from minimal_agora.agents import get_default_provider, invoke_agent, set_default_provider
from minimal_agora.models import AgentConfig, AgentRole
from minimal_agora.providers import (
    AgentInvocationResult,
    AgentProvider,
    AnthropicAPIProvider,
    ClaudeSubprocessProvider,
    LiteLLMProvider,
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


class TestAnthropicAPIProvider:
    def test_default_params(self) -> None:
        provider = AnthropicAPIProvider()
        assert provider.model == "claude-sonnet-4-20250514"
        assert provider.max_tokens == 4096
        assert provider.temperature == 1.0
        assert provider.max_retries == 2
        assert provider.api_key is None
        assert provider.base_url is None

    def test_custom_params(self) -> None:
        provider = AnthropicAPIProvider(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            temperature=0.5,
            max_retries=5,
            api_key="sk-test",
            base_url="http://localhost:8080",
        )
        assert provider.model == "claude-haiku-4-5-20251001"
        assert provider.max_tokens == 1024
        assert provider.temperature == 0.5
        assert provider.max_retries == 5
        assert provider.api_key == "sk-test"
        assert provider.base_url == "http://localhost:8080"

    def test_satisfies_protocol(self) -> None:
        assert isinstance(AnthropicAPIProvider(), AgentProvider)

    def test_invoke_calls_messages_create(self) -> None:
        mock_response = MagicMock()
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 20
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "hello world"
        mock_response.content = [text_block]
        mock_response.model = "claude-sonnet-4-20250514"

        mock_create = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.messages.create = mock_create

        with patch(
            "minimal_agora.providers.api_provider._HAS_ANTHROPIC", True
        ), patch(
            "minimal_agora.providers.api_provider.anthropic"
        ) as mock_anthropic:
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            provider = AnthropicAPIProvider()
            with tempfile.TemporaryDirectory() as tmp:
                result = asyncio.run(provider.invoke("test prompt", Path(tmp)))

        mock_create.assert_awaited_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["model"] == "claude-sonnet-4-20250514"
        assert call_kwargs["messages"] == [{"role": "user", "content": "test prompt"}]
        assert call_kwargs["max_tokens"] == 4096
        assert call_kwargs["temperature"] == 1.0

        assert result.output == "hello world"
        assert result.tokens_used == 30
        assert result.input_tokens == 10
        assert result.output_tokens == 20
        assert result.model == "claude-sonnet-4-20250514"

    def test_invoke_passes_api_key_and_base_url_to_client(self) -> None:
        mock_response = MagicMock()
        mock_response.usage.input_tokens = 1
        mock_response.usage.output_tokens = 1
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "ok"
        mock_response.content = [text_block]
        mock_response.model = "m"

        mock_create = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.messages.create = mock_create

        with patch(
            "minimal_agora.providers.api_provider._HAS_ANTHROPIC", True
        ), patch(
            "minimal_agora.providers.api_provider.anthropic"
        ) as mock_anthropic:
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            provider = AnthropicAPIProvider(
                api_key="sk-explicit", base_url="http://localhost:9090"
            )
            with tempfile.TemporaryDirectory() as tmp:
                asyncio.run(provider.invoke("p", Path(tmp)))

        client_kwargs = mock_anthropic.AsyncAnthropic.call_args[1]
        assert client_kwargs["api_key"] == "sk-explicit"
        assert client_kwargs["base_url"] == "http://localhost:9090"

    def test_client_reused_across_invokes(self) -> None:
        mock_response = MagicMock()
        mock_response.usage.input_tokens = 1
        mock_response.usage.output_tokens = 1
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "ok"
        mock_response.content = [text_block]
        mock_response.model = "m"

        mock_create = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.messages.create = mock_create

        with patch(
            "minimal_agora.providers.api_provider._HAS_ANTHROPIC", True
        ), patch(
            "minimal_agora.providers.api_provider.anthropic"
        ) as mock_anthropic:
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            provider = AnthropicAPIProvider()
            with tempfile.TemporaryDirectory() as tmp:
                asyncio.run(provider.invoke("a", Path(tmp)))
                asyncio.run(provider.invoke("b", Path(tmp)))

        # The HTTP client must be constructed once and shared, not rebuilt
        # per invocation — otherwise concurrent runs leak connection pools.
        mock_anthropic.AsyncAnthropic.assert_called_once()
        assert mock_create.await_count == 2

    def test_invoke_without_anthropic_raises(self) -> None:
        with patch("minimal_agora.providers.api_provider._HAS_ANTHROPIC", False):
            provider = AnthropicAPIProvider()
            with tempfile.TemporaryDirectory() as tmp:
                try:
                    asyncio.run(provider.invoke("test", Path(tmp)))
                    assert False, "Should have raised RuntimeError"
                except RuntimeError as e:
                    assert "anthropic package not installed" in str(e)


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
            "1",
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
            assert result.output == "mock output"
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
        assert result.output == "explicit output"
        assert explicit.call_count == 1


class TestLiteLLMProvider:
    def test_default_params(self) -> None:
        provider = LiteLLMProvider()
        assert provider.model == "claude-sonnet-4-20250514"
        assert provider.max_tokens == 4096
        assert provider.temperature == 1.0
        assert provider.api_base is None
        assert provider.api_key is None

    def test_custom_params(self) -> None:
        provider = LiteLLMProvider(
            model="openai/gpt-4o",
            max_tokens=2048,
            temperature=0.7,
            api_base="http://localhost:8000",
            api_key="test-key",
        )
        assert provider.model == "openai/gpt-4o"
        assert provider.max_tokens == 2048
        assert provider.temperature == 0.7
        assert provider.api_base == "http://localhost:8000"
        assert provider.api_key == "test-key"

    def test_satisfies_protocol(self) -> None:
        assert isinstance(LiteLLMProvider(), AgentProvider)

    def test_invoke_calls_acompletion(self) -> None:
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 50
        mock_usage.completion_tokens = 100

        mock_choice = MagicMock()
        mock_choice.message.content = '{"agent": "test", "result": "ok"}'

        mock_response = MagicMock()
        mock_response.usage = mock_usage
        mock_response.model = "openai/gpt-4o"
        mock_response.choices = [mock_choice]

        with patch(
            "minimal_agora.providers.litellm_provider.litellm"
        ) as mock_litellm, patch(
            "minimal_agora.providers.litellm_provider._HAS_LITELLM", True
        ):
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            provider = LiteLLMProvider(model="openai/gpt-4o")
            with tempfile.TemporaryDirectory() as tmp:
                result = asyncio.run(provider.invoke("test prompt", Path(tmp)))

            mock_litellm.acompletion.assert_awaited_once()
            call_kwargs = mock_litellm.acompletion.call_args[1]
            assert call_kwargs["model"] == "openai/gpt-4o"
            assert call_kwargs["messages"] == [{"role": "user", "content": "test prompt"}]
            assert call_kwargs["max_tokens"] == 4096

            assert result.output == '{"agent": "test", "result": "ok"}'
            assert result.tokens_used == 150
            assert result.model == "openai/gpt-4o"
            assert result.input_tokens == 50
            assert result.output_tokens == 100

    def test_invoke_passes_api_base(self) -> None:
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 20

        mock_choice = MagicMock()
        mock_choice.message.content = "response"

        mock_response = MagicMock()
        mock_response.usage = mock_usage
        mock_response.model = "local-model"
        mock_response.choices = [mock_choice]

        with patch(
            "minimal_agora.providers.litellm_provider.litellm"
        ) as mock_litellm, patch(
            "minimal_agora.providers.litellm_provider._HAS_LITELLM", True
        ):
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            provider = LiteLLMProvider(
                model="local-model",
                api_base="http://localhost:8000",
                api_key="sk-test",
            )
            with tempfile.TemporaryDirectory() as tmp:
                asyncio.run(provider.invoke("prompt", Path(tmp)))

            call_kwargs = mock_litellm.acompletion.call_args[1]
            assert call_kwargs["api_base"] == "http://localhost:8000"
            assert call_kwargs["api_key"] == "sk-test"

    def test_invoke_without_litellm_raises(self) -> None:
        with patch("minimal_agora.providers.litellm_provider._HAS_LITELLM", False):
            provider = LiteLLMProvider()
            with tempfile.TemporaryDirectory() as tmp:
                try:
                    asyncio.run(provider.invoke("test", Path(tmp)))
                    assert False, "Should have raised RuntimeError"
                except RuntimeError as e:
                    assert "litellm package not installed" in str(e)


class TestTopLevelExports:
    def test_provider_exports(self) -> None:
        import minimal_agora

        assert hasattr(minimal_agora, "AgentProvider")
        assert hasattr(minimal_agora, "AgentInvocationResult")
        assert hasattr(minimal_agora, "ClaudeSubprocessProvider")
        assert hasattr(minimal_agora, "MockProvider")
        assert hasattr(minimal_agora, "set_default_provider")

    def test_api_provider_export(self) -> None:
        import minimal_agora

        assert hasattr(minimal_agora, "AnthropicAPIProvider")
        assert minimal_agora.AnthropicAPIProvider is AnthropicAPIProvider

    def test_litellm_provider_export(self) -> None:
        import minimal_agora

        assert hasattr(minimal_agora, "LiteLLMProvider")
        assert minimal_agora.LiteLLMProvider is LiteLLMProvider

    def test_all_contains_provider_names(self) -> None:
        import minimal_agora

        expected = {
            "AgentProvider",
            "AgentInvocationResult",
            "AnthropicAPIProvider",
            "ClaudeSubprocessProvider",
            "LiteLLMProvider",
            "MockProvider",
            "set_default_provider",
        }
        assert expected.issubset(set(minimal_agora.__all__))
