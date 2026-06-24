from __future__ import annotations
import base64
import json
import logging

import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)


async def assert_visual(
    screenshot_path: str,
    prompt: str,
    *,
    timeout: int = 30,
) -> dict:
    """Call VLM to verify a visual condition on a screenshot.

    Returns:
        {"passed": bool, "reason": str}

    Uses the default LLMConfig if available, otherwise falls back to
    the VLM_ENDPOINT / VLM_API_KEY env vars.
    """
    import os

    vlm_endpoint = os.getenv("VLM_ENDPOINT", "https://api.openai.com/v1/chat/completions")
    vlm_api_key = os.getenv("VLM_API_KEY", "")
    vlm_model = os.getenv("VLM_MODEL", "gpt-4o")

    # ── load and base64-encode the screenshot ──
    try:
        with open(screenshot_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
    except FileNotFoundError:
        return {"passed": False, "reason": f"Screenshot not found: {screenshot_path}"}

    # ── build the message ──
    system_msg = (
        "You are a visual verification assistant. "
        "You will be shown a screenshot and asked whether a specific "
        "visual condition is true. "
        'Respond ONLY with JSON: {"passed": true/false, "reason": "..."}'
    )
    user_msg = [
        {"type": "text", "text": prompt},
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{img_b64}"},
        },
    ]

    payload = {
        "model": vlm_model,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        "max_tokens": 300,
        "temperature": 0.0,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {vlm_api_key}",
    }

    try:
        # trust_env=False: ignore system proxy env vars for this outbound call
        # (see app/llm/retry.py for rationale).
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            resp = await client.post(vlm_endpoint, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            # Try to parse JSON from the response
            result = json.loads(content)
            return {
                "passed": bool(result.get("passed", False)),
                "reason": result.get("reason", content),
            }
    except Exception as exc:
        logger.exception("VLM call failed")
        return {"passed": False, "reason": f"VLM call error: {exc}"}
