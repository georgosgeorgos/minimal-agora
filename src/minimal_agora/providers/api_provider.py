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
    """Provider that invokes the Anthropic Messages API via the official SDK."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 4096,
        temperature: float = 1.0,
        max_retries: int = 2,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_retries = max_retries

    async def invoke(
        self,
        prompt: str,
        workspace: Path,
        timeout: int = 300,
    ) -> AgentInvocationResult:
        if not _HAS_ANTHROPIC:
            raise RuntimeError("anthropic package not installed")

        client = anthropic.AsyncAnthropic(max_retries=self.max_retries)

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
        )
