from __future__ import annotations

import base64
import logging

from app.llm.schemas import Message, ChatResult, ImageRef, Usage
from app.llm.retry import request_with_retry
from app.llm.protocol import _register

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider:
    """Google Gemini provider."""

    name = "gemini"

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

    async def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> ChatResult:
        url = f"{self._base_url}/models/{self._model}:generateContent?key={self._api_key}"
        payload = self._build_payload(messages, temperature=temperature, max_output_tokens=max_tokens)

        resp = await request_with_retry("POST", url, json=payload)
        data = resp.json()
        return self._parse_response(data)

    async def vision(
        self,
        messages: list[Message],
        images: list[ImageRef],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> ChatResult:
        url = f"{self._base_url}/models/{self._model}:generateContent?key={self._api_key}"
        payload = self._build_vision_payload(
            messages, images, temperature=temperature, max_output_tokens=max_tokens
        )

        resp = await request_with_retry("POST", url, json=payload)
        data = resp.json()
        return self._parse_response(data)

    def _build_payload(
        self,
        messages: list[Message],
        *,
        temperature: float,
        max_output_tokens: int,
    ) -> dict:
        contents = []
        for m in messages:
            role = "user" if m.role in ("user", "system") else "model"
            contents.append({"role": role, "parts": [{"text": m.content}]})

        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
            },
        }
        payload["generationConfig"].update(self._params)
        return payload

    def _build_vision_payload(
        self,
        messages: list[Message],
        images: list[ImageRef],
        *,
        temperature: float,
        max_output_tokens: int,
    ) -> dict:
        # Combine text from all messages
        text_parts = []
        for m in messages:
            text_parts.append(m.content)
        combined_text = "\n".join(text_parts)

        parts: list[dict] = [{"text": combined_text}]
        for img in images:
            if img.type == "url":
                # Gemini does not support URL images directly; fetch and convert
                parts.append({"text": f"[Image: {img.data}]"})
            else:
                parts.append({
                    "inlineData": {
                        "mimeType": img.media_type,
                        "data": img.data,
                    }
                })

        payload: dict = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
            },
        }
        payload["generationConfig"].update(self._params)
        return payload

    @staticmethod
    def _parse_response(data: dict) -> ChatResult:
        content = ""
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            content = "".join(p.get("text", "") for p in parts)

        usage_raw = data.get("usageMetadata", {})
        usage = Usage(
            prompt_tokens=usage_raw.get("promptTokenCount", 0),
            completion_tokens=usage_raw.get("candidatesTokenCount", 0),
            total_tokens=usage_raw.get("totalTokenCount", 0),
        )

        return ChatResult(
            content=content,
            usage=usage,
            model=data.get("modelVersion", ""),
            raw=data,
        )


_register(GeminiProvider)
