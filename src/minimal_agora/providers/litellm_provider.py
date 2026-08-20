from __future__ import annotations

import time
from pathlib import Path

import structlog

from minimal_agora.providers.protocol import AgentInvocationResult

logger = structlog.stdlib.get_logger(__name__)

try:
    import litellm  # type: ignore[import-not-found]

    _HAS_LITELLM = True
except ImportError:
    _HAS_LITELLM = False


class LiteLLMProvider:
    """Provider that invokes any LLM via litellm's unified interface.

    Supports 100+ providers (OpenAI, Anthropic, Cohere, local endpoints, etc.)
    through litellm's model routing. Pass `api_base` for OpenAI-compatible
    local endpoints.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 4096,
        temperature: float = 1.0,
        api_base: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.api_base = api_base
        self.api_key = api_key

    async def invoke(
        self,
        prompt: str,
        workspace: Path,
        timeout: int = 300,
    ) -> AgentInvocationResult:
        if not _HAS_LITELLM:
            raise RuntimeError(
                "litellm package not installed — install with: pip install 'minimal-agora[litellm]'"
            )

        logger.debug(
            "provider.invoke",
            provider="litellm",
            model=self.model,
            api_base=self.api_base,
            workspace=str(workspace),
        )

        t0 = time.monotonic()

        kwargs: dict = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "timeout": timeout,
        }
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if self.api_key:
            kwargs["api_key"] = self.api_key

        response = await litellm.acompletion(**kwargs)

        elapsed = time.monotonic() - t0
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else None
        output_tokens = usage.completion_tokens if usage else None
        tokens_used = (input_tokens or 0) + (output_tokens or 0) if usage else None

        logger.debug(
            "provider.invoke.done",
            provider="litellm",
            model=getattr(response, "model", self.model),
            tokens_used=tokens_used,
            elapsed_s=round(elapsed, 2),
        )

        output = response.choices[0].message.content or ""

        return AgentInvocationResult(
            output=output,
            tokens_used=tokens_used,
            model=getattr(response, "model", self.model),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
