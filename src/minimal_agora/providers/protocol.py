from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class AgentInvocationResult:
    """Result returned by an AgentProvider invocation."""

    output: str
    tokens_used: int | None = field(default=None)
    model: str | None = field(default=None)
    input_tokens: int | None = field(default=None)
    output_tokens: int | None = field(default=None)


@runtime_checkable
class AgentProvider(Protocol):
    """Structural interface for LLM agent invocation backends."""

    async def invoke(
        self,
        prompt: str,
        workspace: Path,
        timeout: int = 300,
        model: str | None = None,
        temperature: float | None = None,
    ) -> AgentInvocationResult: ...
