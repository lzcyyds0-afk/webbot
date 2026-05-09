from __future__ import annotations

import logging

from app.llm.schemas import Message, ChatResult, ImageRef, Usage
from app.llm.retry import request_with_retry
from app.llm.protocol import _register

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.anthropic.com"


class AnthropicProvider:
    """Anthropic Claude provider.

    Uses the Messages API: POST /v1/messages
    """

    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None,
        model: str,
        params: dict,
    ) -> None:
        self._api_key = api_key
        self._base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        self._model = model
        self._params = params

    # ── chat ──

    async def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> ChatResult:
        url = f"{self._base_url}/v1/messages"
        payload = self._build_payload(messages, temperature=temperature, max_tokens=max_tokens)
        headers = self._headers()

        resp = await request_with_retry("POST", url, headers=headers, json=payload)
        data = resp.json()
        return self._parse_response(data)

    # ── vision ──

    async def vision(
        self,
        messages: list[Message],
        images: list[ImageRef],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> ChatResult:
        url = f"{self._base_url}/v1/messages"
        payload = self._build_vision_payload(
            messages, images, temperature=temperature, max_tokens=max_tokens
        )
        headers = self._headers()

        resp = await request_with_retry("POST", url, headers=headers, json=payload)
        data = resp.json()
        return self._parse_response(data)

    # ── internals ──

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
        }

    def _build_payload(
        self,
        messages: list[Message],
        *,
        temperature: float,
        max_tokens: int,
    ) -> dict:
        system, msgs = self._split_system(messages)
        payload: dict = {
            "model": self._model,
            "messages": msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            payload["system"] = system
        payload.update(self._params)
        return payload

    def _build_vision_payload(
        self,
        messages: list[Message],
        images: list[ImageRef],
        *,
        temperature: float,
        max_tokens: int,
    ) -> dict:
        system, msgs = self._split_system(messages)

        # Build image content blocks
        image_blocks = []
        for img in images:
            if img.type == "base64":
                source = {
                    "type": "base64",
                    "media_type": img.media_type,
                    "data": img.data,
                }
            else:
                # Anthropic doesn't support URL images directly in the
                # Messages API; we must download and base64-encode.
                # For simplicity, we pass as-is and let the API reject
                # if it's a URL. Caller should use base64 type.
                source = {
                    "type": "base64",
                    "media_type": img.media_type,
                    "data": img.data,
                }
            image_blocks.append({
                "type": "image",
                "source": source,
            })

        # Append images to the last user message
        if msgs and msgs[-1]["role"] == "user":
            original = msgs[-1]["content"]
            if isinstance(original, str):
                msgs[-1]["content"] = [{"type": "text", "text": original}]
            msgs[-1]["content"].extend(image_blocks)
        else:
            msgs.append({"role": "user", "content": image_blocks})

        payload: dict = {
            "model": self._model,
            "messages": msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            payload["system"] = system
        payload.update(self._params)
        return payload

    @staticmethod
    def _split_system(messages: list[Message]) -> tuple[str, list[dict]]:
        """Extract system message; convert rest to Anthropic format."""
        system = ""
        msgs = []
        for m in messages:
            if m.role == "system":
                system = m.content
            else:
                msgs.append({"role": m.role, "content": m.content})
        return system, msgs

    @staticmethod
    def _parse_response(data: dict) -> ChatResult:
        content = ""
        content_blocks = data.get("content", [])
        if content_blocks:
            # Concatenate all text blocks
            parts = [
                b["text"] for b in content_blocks if b.get("type") == "text"
            ]
            content = "\n".join(parts)

        usage_raw = data.get("usage", {})
        usage = Usage(
            prompt_tokens=usage_raw.get("input_tokens", 0),
            completion_tokens=usage_raw.get("output_tokens", 0),
            total_tokens=usage_raw.get("input_tokens", 0) + usage_raw.get("output_tokens", 0),
        )

        return ChatResult(
            content=content,
            usage=usage,
            model=data.get("model", ""),
            raw=data,
        )


_register(AnthropicProvider)
