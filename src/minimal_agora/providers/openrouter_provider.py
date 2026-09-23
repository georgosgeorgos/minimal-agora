from __future__ import annotations

from minimal_agora.providers.litellm_provider import LiteLLMProvider

DEFAULT_OPENROUTER_MODEL = "deepseek/deepseek-v4.1-flash"


class OpenRouterProvider(LiteLLMProvider):
    """OpenRouter API provider with DeepSeek V4.1 Flash as the default model."""

    def __init__(
        self,
        model: str = DEFAULT_OPENROUTER_MODEL,
        api_key: str | None = None,
        api_base: str | None = None,
        disable_reasoning: bool | None = None,
    ) -> None:
        model = model.removeprefix("openrouter/")
        if disable_reasoning is None:
            disable_reasoning = model == DEFAULT_OPENROUTER_MODEL
        super().__init__(
            model=f"openrouter/{model}",
            api_key=api_key,
            api_base=api_base,
            disable_reasoning=disable_reasoning,
        )
