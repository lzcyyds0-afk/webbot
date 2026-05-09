"""Sanitize sensitive data from run exports."""
from __future__ import annotations

import re
from typing import Any

# Keys whose values should be masked in JSON payloads
_SENSITIVE_KEYS = {
    "api_key", "apikey", "api-key", "token", "access_token", "refresh_token",
    "password", "secret", "client_secret", "auth", "authorization",
    "cookie", "session", "credentials", "key",
}

# URL query params to mask
_SENSITIVE_QUERY_PARAMS = {
    "token", "api_key", "apikey", "api-key", "key", "secret", "auth",
    "access_token", "refresh_token", "password", "session",
}

_MASK = "***"


def _mask_value(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: _MASK if k.lower() in _SENSITIVE_KEYS else _mask_value(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_mask_value(v) for v in obj]
    return obj


def sanitize_input_output(data: dict | None) -> dict | None:
    """Mask sensitive fields in step input/output JSON."""
    if data is None:
        return None
    return _mask_value(data)


def sanitize_console_logs(logs: list[dict]) -> list[dict]:
    """Mask tokens and keys in console log messages."""
    out: list[dict] = []
    for log in logs:
        text = str(log.get("text", ""))
        # Simple regex to mask common patterns
        text = re.sub(
            r"([\"']?(?:api[_-]?key|token|secret|password)[\"']?\s*[:=]\s*[\"']?)[^\s\"'&,]+",
            r"\1***",
            text,
            flags=re.IGNORECASE,
        )
        out.append({**log, "text": text})
    return out


def sanitize_network_requests(requests: list[dict]) -> list[dict]:
    """Mask sensitive query params in network request URLs."""
    out: list[dict] = []
    for req in requests:
        url = str(req.get("url", ""))
        # Mask sensitive query parameters
        for param in _SENSITIVE_QUERY_PARAMS:
            url = re.sub(
                rf"([?&]{param}=)[^&]*",
                rf"\1***",
                url,
                flags=re.IGNORECASE,
            )
        out.append({**req, "url": url})
    return out


def sanitize_step_error(error: str | None) -> str | None:
    """Mask sensitive data in error messages."""
    if not error:
        return error
    error = re.sub(
        r"([\"']?(?:api[_-]?key|token|secret|password)[\"']?\s*[:=]\s*[\"']?)[^\s\"'&,]+",
        r"\1***",
        error,
        flags=re.IGNORECASE,
    )
    return error
