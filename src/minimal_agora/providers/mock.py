from __future__ import annotations

from pathlib import Path

import structlog

from minimal_agora.providers.protocol import AgentInvocationResult

logger = structlog.stdlib.get_logger(__name__)


class MockProvider:
    """Provider that returns pre-configured responses for testing."""

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self.responses: dict[str, str] = responses or {}
        self.call_count: int = 0
        self.last_prompt: str | None = None

    async def invoke(
        self,
        prompt: str,
        workspace: Path,
        timeout: int = 300,
        model: str | None = None,
        temperature: float | None = None,
    ) -> AgentInvocationResult:
        self.call_count += 1
        self.last_prompt = prompt
        self.last_temperature = temperature

        prompt_lower = prompt.lower()
        response = "Mock response"
        for key, value in self.responses.items():
            if key.lower() in prompt_lower:
                response = value
                break

        logger.debug(
            "provider.invoke.done",
            provider="mock",
            output_length=len(response),
            tokens_used=100,
        )

        return AgentInvocationResult(
            output=response,
            tokens_used=100,
            model=model or "mock-model",
        )
