"""Unit tests for app.engine.actions — ActionExecutor and its helpers.

A fake Playwright Page (MagicMock with AsyncMock methods) stands in for a real
browser, so these tests run offline and in milliseconds.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from playwright.async_api import TimeoutError as PwTimeout

from app.engine.actions import (
    ActionExecutor,
    _extract_selector,
    _apply_healed_selector,
    _heal_output,
    _format_error,
)
from app.engine.models import StepContext
from app.engine.self_heal import HealResult
from app.models.run_step import StepStatus


def make_page(**overrides) -> MagicMock:
    page = MagicMock()
    page.url = "https://example.com/page"
    page.goto = AsyncMock()
    page.title = AsyncMock(return_value="Title")
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.wait_for_selector = AsyncMock()
    for k, v in overrides.items():
        setattr(page, k, v)
    return page


def ctx(action: str, **params) -> StepContext:
    return StepContext(
        run_id=1,
        step_index=0,
        action=action,
        params=params,
        base_url="https://example.com",
    )


# ── action handlers ──

class TestActionHandlers:
    @pytest.mark.asyncio
    async def test_goto_relative_url_joined_with_base(self):
        page = make_page()
        result = await ActionExecutor().execute(page, ctx("goto", url="login"))
        assert result.status == StepStatus.passed
        page.goto.assert_awaited_once()
        assert page.goto.call_args.args[0] == "https://example.com/login"

    @pytest.mark.asyncio
    async def test_goto_absolute_url_kept(self):
        page = make_page()
        await ActionExecutor().execute(page, ctx("goto", url="https://other.com/x"))
        assert page.goto.call_args.args[0] == "https://other.com/x"

    @pytest.mark.asyncio
    async def test_click_success(self):
        page = make_page()
        result = await ActionExecutor().execute(page, ctx("click", selector="#btn"))
        assert result.status == StepStatus.passed
        page.click.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_input_fills_text(self):
        page = make_page()
        result = await ActionExecutor().execute(page, ctx("input", selector="#in", text="hi"))
        assert result.status == StepStatus.passed
        assert page.fill.call_args.args == ("#in", "hi")

    @pytest.mark.asyncio
    async def test_wait_requires_ms_or_selector(self):
        page = make_page()
        result = await ActionExecutor().execute(page, ctx("wait"))
        assert result.status == StepStatus.failed
        assert "requires" in result.error

    @pytest.mark.asyncio
    async def test_unknown_action_fails(self):
        page = make_page()
        result = await ActionExecutor().execute(page, ctx("frobnicate"))
        assert result.status == StepStatus.failed
        assert "Unknown action" in result.error

    @pytest.mark.asyncio
    async def test_timeout_error_is_prefixed(self):
        page = make_page(click=AsyncMock(side_effect=PwTimeout("Timeout 15000ms exceeded")))
        result = await ActionExecutor().execute(page, ctx("click", selector="#btn"))
        assert result.status == StepStatus.failed
        assert result.error.startswith("Timeout:")

    @pytest.mark.asyncio
    async def test_generic_error_not_prefixed(self):
        page = make_page(fill=AsyncMock(side_effect=ValueError("boom")))
        result = await ActionExecutor().execute(page, ctx("input", selector="#in", text="x"))
        assert result.status == StepStatus.failed
        assert result.error == "boom"


# ── self-heal integration in execute() ──

class TestSelfHealTrigger:
    @pytest.mark.asyncio
    async def test_unhealthy_selector_triggers_heal_and_uses_new_selector(self):
        # locator().count() == 0 → selector unhealthy → heal kicks in
        loc = MagicMock()
        loc.count = AsyncMock(return_value=0)
        page = make_page(locator=MagicMock(return_value=loc))

        heal_engine = MagicMock()
        heal_engine.try_heal = AsyncMock(
            return_value=HealResult(healed_selector="#healed", method="rule")
        )

        c = ctx("click", selector="#broken")
        result = await ActionExecutor(heal_engine=heal_engine).execute(page, c)

        assert result.status == StepStatus.passed
        heal_engine.try_heal.assert_awaited_once()
        # The click used the healed selector and heal metadata was recorded.
        assert page.click.call_args.args[0] == "#healed"
        assert c.params["_healed"] is True
        assert c.params["_original_selector"] == "#broken"
        assert result.output_json["healed"] is True


# ── pure helpers ──

class TestPureHelpers:
    def test_extract_selector_per_action(self):
        assert _extract_selector(ctx("click", selector="#a")) == "#a"
        assert _extract_selector(ctx("input", selector="#b")) == "#b"
        assert _extract_selector(ctx("wait", selector="#c")) == "#c"
        assert _extract_selector(ctx("drag", from_selector="#f")) == "#f"
        assert _extract_selector(ctx("connect", from_port_selector="#p")) == "#p"
        assert _extract_selector(ctx("goto", url="/")) is None

    def test_apply_healed_selector_click(self):
        c = ctx("click", selector="#old")
        original = _apply_healed_selector(c, "#new")
        assert original == "#old"
        assert c.params["selector"] == "#new"
        assert c.params["_healed"] is True
        assert c.params["_healed_selector"] == "#new"

    def test_heal_output_defaults(self):
        out = _heal_output(ctx("click", selector="#a"))
        assert out["healed"] is False
        assert out["healed_selector"] is None

    def test_format_error_timeout(self):
        assert _format_error(PwTimeout("Timeout 1000ms")).startswith("Timeout:")

    def test_format_error_generic(self):
        assert _format_error(ValueError("nope")) == "nope"
