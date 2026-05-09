"""Signed URL tokens for secure export downloads."""
from __future__ import annotations

import base64
import hmac
import hashlib
import time

from app.core.config import settings


def sign_export_token(run_id: int, filename: str, expires_in: int = 86400) -> str:
    """Sign a download token valid for `expires_in` seconds (default 24h).

    Returns a URL-safe base64 string.
    """
    expires_at = int(time.time()) + expires_in
    payload = f"{run_id}:{filename}:{expires_at}"
    sig = hmac.new(
        settings.secret_key.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()[:20]
    token = base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()
    return token


def verify_export_token(token: str, run_id: int, filename: str) -> bool:
    """Verify token signature and expiration."""
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        parts = decoded.rsplit(":", 1)
        if len(parts) != 2:
            return False
        payload, sig = parts
        expected_sig = hmac.new(
            settings.secret_key.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()[:20]
        if not hmac.compare_digest(sig, expected_sig):
            return False
        payload_parts = payload.split(":")
        if len(payload_parts) != 3:
            return False
        t_run_id, t_filename, t_expires = payload_parts
        if int(t_run_id) != run_id or t_filename != filename:
            return False
        if int(t_expires) < time.time():
            return False
        return True
    except Exception:
        return False
