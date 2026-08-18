"""Pluggable agent provider abstraction for LLM invocation backends."""

from minimal_agora.providers.mock import MockProvider
from minimal_agora.providers.protocol import AgentInvocationResult, AgentProvider
from minimal_agora.providers.subprocess_provider import ClaudeSubprocessProvider

__all__ = [
    "AgentInvocationResult",
    "AgentProvider",
    "ClaudeSubprocessProvider",
    "MockProvider",
]
