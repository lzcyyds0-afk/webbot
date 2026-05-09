from __future__ import annotations

import logging

from app.llm.schemas import Message, ChatResult, ImageRef, Usage
from app.llm.retry import request_with_retry
from app.llm.protocol import _register

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.openai.com/v1"


class OpenAIProvider:
    """OpenAI-compatible provider.

    Works with: OpenAI, DeepSeek, Qwen DashScope, and any
    OpenAI-compatible endpoint.

    DeepSeek:   base_url = "https://api.deepseek.com/v1"
    DashScope:  base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    """

    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None,
        model: str,
        params: dict,
    ) -> None:
        self._api_key = api_key
        raw = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        # Defensive: users sometimes paste the full endpoint URL as base_url
        if raw.endswith("/chat/completions"):
            raw = raw[: -len("/chat/completions")]
        self._base_url = raw
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
        url = f"{self._base_url}/chat/completions"
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
        url = f"{self._base_url}/chat/completions"
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
            "Authorization": f"Bearer {self._api_key}",
        }

    def _build_payload(
        self,
        messages: list[Message],
        *,
        temperature: float,
        max_tokens: int,
    ) -> dict:
        msgs = [{"role": m.role, "content": m.content} for m in messages]
        payload: dict = {
            "model": self._model,
            "messages": msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        # Merge extra params (e.g. top_p, frequency_penalty)
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
        msgs = []
        for m in messages:
            msgs.append({"role": m.role, "content": m.content})

        # Append images as image_url content blocks to the last user message
        image_blocks = []
        for img in images:
            if img.type == "url":
                image_url = img.data
            else:
                image_url = f"data:{img.media_type};base64,{img.data}"
            image_blocks.append({
                "type": "image_url",
                "image_url": {"url": image_url},
            })

        # Find last user message and append images to it
        if msgs and msgs[-1]["role"] == "user":
            original_content = msgs[-1]["content"]
            msgs[-1]["content"] = [
                {"type": "text", "text": original_content},
                *image_blocks,
            ]
        else:
            # No user message; add one with just images
            msgs.append({"role": "user", "content": image_blocks})

        payload: dict = {
            "model": self._model,
            "messages": msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        payload.update(self._params)
        return payload

    @staticmethod
    def _parse_response(data: dict) -> ChatResult:
        content = ""
        choices = data.get("choices", [])
        if choices:
            delta = choices[0].get("message", {})
            content = delta.get("content", "")

        usage_raw = data.get("usage", {})
        usage = Usage(
            prompt_tokens=usage_raw.get("prompt_tokens", 0),
            completion_tokens=usage_raw.get("completion_tokens", 0),
            total_tokens=usage_raw.get("total_tokens", 0),
        )

        return ChatResult(
            content=content,
            usage=usage,
            model=data.get("model", ""),
            raw=data,
        )


_register(OpenAIProvider)
