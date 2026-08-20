from __future__ import annotations

import time
from pathlib import Path

import structlog

from minimal_agora.providers.protocol import AgentInvocationResult

logger = structlog.stdlib.get_logger(__name__)

try:
    import anthropic  # type: ignore[import-not-found]

    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False


class AnthropicAPIProvider:
    """Provider that invokes the Anthropic Messages API via the official SDK.

    The HTTP client is constructed once (lazily, on first use) and reused
    across invocations so that connection pools are shared under concurrent
    runs. ``api_key`` / ``base_url`` default to ``None``, which lets the SDK
    fall back to ``ANTHROPIC_API_KEY`` / ``ANTHROPIC_BASE_URL`` environment
    variables — pass them explicitly (e.g. via the CLI ``--api-key`` /
    ``--api-base`` flags) to override.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 2048,
        temperature: float = 1.0,
        max_retries: int = 2,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_retries = max_retries
        self.api_key = api_key
        self.base_url = base_url
        # Constructed lazily so the provider can be instantiated without the
        # `anthropic` extra installed (mirrors the LiteLLMProvider pattern).
        self._client = None

    def _get_client(self):  # type: ignore[no-untyped-def]
        """Return the shared AsyncAnthropic client, creating it on first use."""
        if self._client is None:
            if not _HAS_ANTHROPIC:
                raise RuntimeError(
                    "anthropic package not installed — install with: "
                    "pip install 'minimal-agora[api]'"
                )
            self._client = anthropic.AsyncAnthropic(
                api_key=self.api_key,
                base_url=self.base_url,
                max_retries=self.max_retries,
            )
        return self._client

    async def invoke(
        self,
        prompt: str,
        workspace: Path,
        timeout: int = 300,
    ) -> AgentInvocationResult:
        client = self._get_client()

        logger.debug(
            "provider.invoke",
            provider="anthropic-api",
            model=self.model,
            workspace=str(workspace),
        )

        t0 = time.monotonic()

        response = await client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}],
        )

        elapsed = time.monotonic() - t0
        tokens_used = response.usage.input_tokens + response.usage.output_tokens

        logger.debug(
            "provider.invoke.done",
            provider="anthropic-api",
            model=response.model,
            tokens_used=tokens_used,
            elapsed_s=round(elapsed, 2),
            output_length=sum(
                len(block.text) for block in response.content if block.type == "text"
            ),
        )

        output = next(
            (block.text for block in response.content if block.type == "text"),
            "",
        )

        return AgentInvocationResult(
            output=output,
            tokens_used=tokens_used,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
