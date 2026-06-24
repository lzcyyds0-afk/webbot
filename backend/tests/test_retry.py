"""Unit tests for app.llm.retry.request_with_retry.

httpx.AsyncClient is replaced with a mock so no real network call happens, and
asyncio.sleep is patched out so retries don't actually wait.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.llm.retry import request_with_retry


def _resp(status: int) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.request = MagicMock()
    if 400 <= status < 500:
        r.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError("client error", request=r.request, response=r)
        )
    else:
        r.raise_for_status = MagicMock()
    return r


def _patch_client(request_side_effect):
    """Patch app.llm.retry.httpx.AsyncClient so each construction yields a client
    whose .request follows request_side_effect (a list of responses/exceptions)."""
    client = MagicMock()
    client.request = AsyncMock(side_effect=request_side_effect)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return patch("app.llm.retry.httpx.AsyncClient", return_value=client), client


@pytest.fixture(autouse=True)
def _no_sleep():
    with patch("app.llm.retry.asyncio.sleep", new=AsyncMock()):
        yield


class TestRequestWithRetry:
    @pytest.mark.asyncio
    async def test_success_returns_immediately(self):
        ok = _resp(200)
        cm, client = _patch_client([ok])
        with cm:
            resp = await request_with_retry("GET", "http://x")
        assert resp is ok
        assert client.request.await_count == 1

    @pytest.mark.asyncio
    async def test_4xx_raises_without_retry(self):
        cm, client = _patch_client([_resp(404)])
        with cm, pytest.raises(httpx.HTTPStatusError):
            await request_with_retry("GET", "http://x")
        assert client.request.await_count == 1

    @pytest.mark.asyncio
    async def test_5xx_retries_then_raises(self):
        cm, client = _patch_client([_resp(500), _resp(500), _resp(500)])
        with cm, pytest.raises(httpx.HTTPStatusError):
            await request_with_retry("GET", "http://x", max_retries=2)
        # initial attempt + 2 retries
        assert client.request.await_count == 3

    @pytest.mark.asyncio
    async def test_timeout_then_success(self):
        ok = _resp(200)
        cm, client = _patch_client([httpx.TimeoutException("slow"), ok])
        with cm:
            resp = await request_with_retry("GET", "http://x", max_retries=2)
        assert resp is ok
        assert client.request.await_count == 2

    @pytest.mark.asyncio
    async def test_connect_error_exhausts_retries(self):
        cm, client = _patch_client([httpx.ConnectError("down")] * 3)
        with cm, pytest.raises(httpx.ConnectError):
            await request_with_retry("GET", "http://x", max_retries=2)
        assert client.request.await_count == 3
