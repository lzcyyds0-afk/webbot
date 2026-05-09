from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ImageRef(BaseModel):
    type: Literal["url", "base64"] = "url"
    data: str  # URL string or base64-encoded string
    media_type: str = "image/png"


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResult(BaseModel):
    content: str
    usage: Usage = Usage()
    model: str = ""
    raw: dict | None = None
