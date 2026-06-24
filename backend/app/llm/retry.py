from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


async def request_with_retry(
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    json: dict | None = None,
    timeout: float = 30.0,
    max_retries: int = 2,
) -> httpx.Response:
    """HTTP request with retry on transient failures.

    - Retries on: 5xx status, TimeoutError, ConnectError
    - Does NOT retry on 4xx (client error)
    - Exponential backoff: 1s, 2s between retries
    """
    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            # trust_env=False makes this client ignore the process/system proxy
            # env vars (ALL_PROXY/HTTP_PROXY/...), which would otherwise route
            # LLM API calls through a (often SOCKS) proxy and break them.
            # This isolates proxy behaviour to LLM calls without mutating the
            # global environment for the rest of the app (e.g. Playwright).
            async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                resp = await client.request(
                    method,
                    url,
                    headers=headers,
                    json=json,
                )

            # 4xx -> raise immediately, no retry
            if resp.status_code >= 400 and resp.status_code < 500:
                resp.raise_for_status()

            # 5xx -> retry
            if resp.status_code >= 500:
                last_exc = httpx.HTTPStatusError(
                    f"Server error {resp.status_code}",
                    request=resp.request,
                    response=resp,
                )
                if attempt < max_retries:
                    delay = 2**attempt
                    logger.warning(
                        "Request to %s failed with %d, retrying in %ds (attempt %d/%d)",
                        url,
                        resp.status_code,
                        delay,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise last_exc

            return resp

        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            last_exc = exc
            if attempt < max_retries:
                delay = 2**attempt
                logger.warning(
                    "Request to %s failed: %s, retrying in %ds (attempt %d/%d)",
                    url,
                    exc,
                    delay,
                    attempt + 1,
                    max_retries,
                )
                await asyncio.sleep(delay)
                continue
            raise

    # Should not reach here, but just in case
    raise last_exc or RuntimeError("Unexpected retry loop exit")
