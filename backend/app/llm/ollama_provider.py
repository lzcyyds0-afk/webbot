from __future__ import annotations

import base64
import logging

from app.llm.schemas import Message, ChatResult, ImageRef, Usage
from app.llm.retry import request_with_retry
from app.llm.protocol import _register

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaProvider:
    """Ollama local provider."""

    name = "ollama"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None,
        model: str,
        params: dict,
    ) -> None:
        self._api_key = api_key  # Not used for Ollama
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
        url = f"{self._base_url}/api/chat"
        payload = self._build_payload(messages, temperature=temperature, max_tokens=max_tokens)

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
        url = f"{self._base_url}/api/chat"
        payload = self._build_vision_payload(
            messages, images, temperature=temperature, max_tokens=max_tokens
        )

        resp = await request_with_retry("POST", url, json=payload)
        data = resp.json()
        return self._parse_response(data)

    def _build_payload(
        self,
        messages: list[Message],
        *,
        temperature: float,
        max_tokens: int,
    ) -> dict:
        msgs = []
        for m in messages:
            role = m.role
            if role == "system":
                # Ollama treats system messages as a separate field
                continue
            msgs.append({"role": role, "content": m.content})

        # Extract system message if any
        system_content = ""
        for m in messages:
            if m.role == "system":
                system_content = m.content
                break

        payload: dict = {
            "model": self._model,
            "messages": msgs,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if system_content:
            payload["system"] = system_content
        payload["options"].update(self._params)
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
        system_content = ""
        for m in messages:
            if m.role == "system":
                system_content = m.content
                continue
            msgs.append({"role": m.role, "content": m.content})

        # Ollama supports images via "images" field with base64 strings
        image_b64s = []
        for img in images:
            if img.type == "base64":
                image_b64s.append(img.data)
            else:
                # URL images not directly supported; include as text
                if msgs:
                    msgs[-1]["content"] += f"\n[Image: {img.data}]"

        if image_b64s and msgs:
            msgs[-1]["images"] = image_b64s

        payload: dict = {
            "model": self._model,
            "messages": msgs,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if system_content:
            payload["system"] = system_content
        payload["options"].update(self._params)
        return payload

    @staticmethod
    def _parse_response(data: dict) -> ChatResult:
        content = ""
        message = data.get("message", {})
        if message:
            content = message.get("content", "")

        usage = Usage(
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            total_tokens=(data.get("prompt_eval_count", 0) + data.get("eval_count", 0)),
        )

        return ChatResult(
            content=content,
            usage=usage,
            model=data.get("model", ""),
            raw=data,
        )


_register(OllamaProvider)
