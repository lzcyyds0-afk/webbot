"""Unit tests for app.llm.protocol.get_provider — the provider factory.

Importing app.llm registers all four providers. We use a tiny fake config so no
real API key or network is involved.
"""
from __future__ import annotations

import pytest

import app.llm  # noqa: F401 — triggers provider registration
from app.llm.protocol import get_provider


class FakeConfig:
    def __init__(self, provider: str) -> None:
        self.provider = provider
        self.base_url = None
        self.model = "some-model"
        self.params_json = {}

    def get_plain_key(self) -> str:
        return "fake-key"


@pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini", "ollama"])
def test_known_providers_instantiate(provider):
    instance = get_provider(FakeConfig(provider))
    assert instance.name == provider


def test_unknown_provider_raises_with_supported_list():
    with pytest.raises(ValueError) as exc:
        get_provider(FakeConfig("doesnotexist"))
    msg = str(exc.value)
    assert "Unsupported provider" in msg
    # The error lists the supported providers to aid debugging.
    assert "openai" in msg and "anthropic" in msg


def test_params_json_none_is_tolerated():
    cfg = FakeConfig("openai")
    cfg.params_json = None
    instance = get_provider(cfg)
    assert instance.name == "openai"
