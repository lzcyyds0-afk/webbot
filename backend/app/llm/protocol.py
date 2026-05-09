from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.llm.schemas import Message, ChatResult, ImageRef


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    async def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> ChatResult: ...

    async def vision(
        self,
        messages: list[Message],
        images: list[ImageRef],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> ChatResult: ...


# ── Factory ──

_PROVIDER_CLASSES: dict[str, type] = {}


def _register(cls: type) -> None:
    """Register a provider class by its `name` attribute."""
    _PROVIDER_CLASSES[cls.name] = cls


def get_provider(config) -> LLMProvider:
    """Instantiate an LLMProvider from a database LLMConfig.

    The config object must have:
      - config.provider  (str: "openai" | "anthropic" | "gemini" | "ollama")
      - config.get_plain_key() -> str  (decrypted api_key)
      - config.base_url  (str | None)
      - config.model     (str)
      - config.params_json (dict | None)
    """
    cls = _PROVIDER_CLASSES.get(config.provider)
    if cls is None:
        supported = ", ".join(sorted(_PROVIDER_CLASSES.keys()))
        raise ValueError(
            f"Unsupported provider: {config.provider!r}. Supported: {supported}"
        )
    return cls(
        api_key=config.get_plain_key(),
        base_url=config.base_url,
        model=config.model,
        params=config.params_json or {},
    )