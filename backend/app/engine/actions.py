from __future__ import annotations
import asyncio
import time

from playwright.async_api import Page, TimeoutError as PwTimeout

from app.engine.models import StepContext, StepResult
from app.engine.drag_and_connect import do_drag, do_connect
from app.engine.auth import do_login
from app.engine.self_heal import SelfHealEngine
from app.models.run_step import StepStatus


class ActionExecutor:
    _ACTION_MAP: dict[str, str]

    def __init__(self, heal_engine: SelfHealEngine | None = None) -> None:
        self._ACTION_MAP = {
            "goto": self._goto,
            "click": self._click,
            "input": self._input,
            "wait": self._wait,
            "screenshot": self._screenshot,
            "drag": self._drag,
            "connect": self._connect,
            "login": self._login,
        }
        self._heal_engine = heal_engine

    async def execute(self, page: Page, ctx: StepContext) -> StepResult:
        handler = self._ACTION_MAP.get(ctx.action)
        if handler is None:
            return StepResult(
                step_index=ctx.step_index,
                action=ctx.action,
                status=StepStatus.failed,
                duration_ms=0,
                input_json=ctx.params,
                output_json=None,
                screenshot_path=None,
                error=f"Unknown action: {ctx.action}",
            )

        # ── Self-heal: check selector health before action ──
        selector = _extract_selector(ctx)
        if selector and self._heal_engine:
            healthy = await _is_locator_healthy(page, selector)
            if not healthy:
                heal_result = await self._heal_engine.try_heal(page, selector, ctx)
                if heal_result:
                    # Mutate params in place with healed selector
                    _apply_healed_selector(ctx, heal_result.healed_selector)
                    ctx.params["_heal_method"] = heal_result.method

        return await handler(page, ctx)

    # ── goto ──
    async def _goto(self, page: Page, ctx: StepContext) -> StepResult:
        url = ctx.params.get("url", "")
        if url and not url.startswith(("http://", "https://")):
            url = ctx.base_url.rstrip("/") + "/" + url.lstrip("/")
        t0 = time.monotonic()
        try:
            # Use networkidle so dynamic JS content has time to render
            await page.goto(url, wait_until="networkidle", timeout=20_000)
            elapsed = int((time.monotonic() - t0) * 1000)
            return StepResult(
                step_index=ctx.step_index,
                action="goto",
                status=StepStatus.passed,
                duration_ms=elapsed,
                input_json={"url": url},
                output_json={"title": await page.title(), "url": page.url},
                screenshot_path=None,
            )
        except (PwTimeout, Exception) as exc:
            elapsed = int((time.monotonic() - t0) * 1000)
            return StepResult(
                step_index=ctx.step_index,
                action="goto",
                status=StepStatus.failed,
                duration_ms=elapsed,
                input_json={"url": url},
                output_json=None,
                screenshot_path=None,
                error=str(exc),
            )

    # ── click ──
    async def _click(self, page: Page, ctx: StepContext) -> StepResult:
        selector = ctx.params.get("selector", "")
        t0 = time.monotonic()
        try:
            locator = page.locator(selector)
            count = await locator.count()
            if count > 1:
                # Multiple matches: click the first visible one to avoid timing out
                # on a hidden duplicate (e.g. collapsed sidebar entry vs main nav).
                target = None
                for i in range(count):
                    if await locator.nth(i).is_visible():
                        target = locator.nth(i)
                        break
                if target is None:
                    target = locator.first
                await target.click(timeout=15_000)
            else:
                await page.click(selector, timeout=15_000)
            elapsed = int((time.monotonic() - t0) * 1000)
            return StepResult(
                step_index=ctx.step_index,
                action="click",
                status=StepStatus.passed,
                duration_ms=elapsed,
                input_json={"selector": selector},
                output_json={"url": page.url, **_heal_output(ctx)},
                screenshot_path=None,
            )
        except (PwTimeout, Exception) as exc:
            elapsed = int((time.monotonic() - t0) * 1000)
            return StepResult(
                step_index=ctx.step_index,
                action="click",
                status=StepStatus.failed,
                duration_ms=elapsed,
                input_json={"selector": selector},
                output_json=_heal_output(ctx),
                screenshot_path=None,
                error=str(exc),
            )

    # ── input ──
    async def _input(self, page: Page, ctx: StepContext) -> StepResult:
        selector = ctx.params.get("selector", "")
        text = ctx.params.get("text", "")
        t0 = time.monotonic()
        try:
            await page.fill(selector, text, timeout=15_000)
            elapsed = int((time.monotonic() - t0) * 1000)
            return StepResult(
                step_index=ctx.step_index,
                action="input",
                status=StepStatus.passed,
                duration_ms=elapsed,
                input_json={"selector": selector, "text": text},
                output_json={"url": page.url, **_heal_output(ctx)},
                screenshot_path=None,
            )
        except (PwTimeout, Exception) as exc:
            elapsed = int((time.monotonic() - t0) * 1000)
            return StepResult(
                step_index=ctx.step_index,
                action="input",
                status=StepStatus.failed,
                duration_ms=elapsed,
                input_json={"selector": selector, "text": text},
                output_json=_heal_output(ctx),
                screenshot_path=None,
                error=str(exc),
            )

    # ── wait ──
    async def _wait(self, page: Page, ctx: StepContext) -> StepResult:
        ms = ctx.params.get("ms")
        selector = ctx.params.get("selector")
        t0 = time.monotonic()
        try:
            if ms is not None:
                await asyncio.sleep(int(ms) / 1000)
            elif selector:
                await page.wait_for_selector(selector, timeout=15_000)
            else:
                raise ValueError("wait requires 'ms' or 'selector'")
            elapsed = int((time.monotonic() - t0) * 1000)
            return StepResult(
                step_index=ctx.step_index,
                action="wait",
                status=StepStatus.passed,
                duration_ms=elapsed,
                input_json={"ms": ms, "selector": selector},
                output_json=_heal_output(ctx),
                screenshot_path=None,
            )
        except (PwTimeout, Exception) as exc:
            elapsed = int((time.monotonic() - t0) * 1000)
            return StepResult(
                step_index=ctx.step_index,
                action="wait",
                status=StepStatus.failed,
                duration_ms=elapsed,
                input_json={"ms": ms, "selector": selector},
                output_json=_heal_output(ctx),
                screenshot_path=None,
                error=str(exc),
            )

    # ── screenshot ──
    async def _screenshot(self, page: Page, ctx: StepContext) -> StepResult:
        full_page = ctx.params.get("full_page", False)
        t0 = time.monotonic()
        try:
            # actual save is done by Runner via Storage;
            # here we just record the intent
            elapsed = int((time.monotonic() - t0) * 1000)
            return StepResult(
                step_index=ctx.step_index,
                action="screenshot",
                status=StepStatus.passed,
                duration_ms=elapsed,
                input_json={"full_page": full_page},
                output_json={"url": page.url},
                screenshot_path=None,
            )
        except Exception as exc:
            elapsed = int((time.monotonic() - t0) * 1000)
            return StepResult(
                step_index=ctx.step_index,
                action="screenshot",
                status=StepStatus.failed,
                duration_ms=elapsed,
                input_json={"full_page": full_page},
                output_json=None,
                screenshot_path=None,
                error=str(exc),
            )

    # ── drag ──
    async def _drag(self, page: Page, ctx: StepContext) -> StepResult:
        return await do_drag(page, ctx)

    # ── connect ──
    async def _connect(self, page: Page, ctx: StepContext) -> StepResult:
        return await do_connect(page, ctx)

    # ── login ──
    async def _login(self, page: Page, ctx: StepContext) -> StepResult:
        return await do_login(page, ctx)


# ── Helpers ──

def _heal_output(ctx: StepContext) -> dict:
    """Return heal metadata dict for output_json."""
    return {
        "healed": ctx.params.get("_healed", False),
        "healed_selector": ctx.params.get("_healed_selector"),
        "_original_selector": ctx.params.get("_original_selector"),
        "_heal_method": ctx.params.get("_heal_method"),
    }


def _extract_selector(ctx: StepContext) -> str | None:
    """Get the CSS selector from step params if the action uses one."""
    if ctx.action in ("click", "input", "wait"):
        return ctx.params.get("selector")
    if ctx.action == "drag":
        return ctx.params.get("from_selector") or ctx.params.get("to_selector")
    if ctx.action == "connect":
        return ctx.params.get("from_port_selector") or ctx.params.get("to_port_selector")
    return None


async def _is_locator_healthy(page: Page, selector: str) -> bool:
    """Quick check: does the selector find at least one visible element within 3s?"""
    try:
        locator = page.locator(selector)
        count = await locator.count()
        if count == 0:
            return False
        # Consider healthy if any match is visible (not just the first)
        for i in range(count):
            if await locator.nth(i).is_visible():
                return True
        return False
    except (PwTimeout, Exception):
        return False


def _apply_healed_selector(ctx: StepContext, healed_selector: str) -> str:
    """Mutate ctx.params to replace the selector with the healed one, recording the change.
    Returns the original selector."""
    original = ""
    if ctx.action in ("click", "input", "wait"):
        original = ctx.params.get("selector", "")
        ctx.params["selector"] = healed_selector
    elif ctx.action == "drag":
        if "from_selector" in ctx.params:
            original = ctx.params["from_selector"]
            ctx.params["from_selector"] = healed_selector
        elif "to_selector" in ctx.params:
            original = ctx.params["to_selector"]
            ctx.params["to_selector"] = healed_selector
    elif ctx.action == "connect":
        if "from_port_selector" in ctx.params:
            original = ctx.params["from_port_selector"]
            ctx.params["from_port_selector"] = healed_selector
        elif "to_port_selector" in ctx.params:
            original = ctx.params["to_port_selector"]
            ctx.params["to_port_selector"] = healed_selector
    ctx.params["_healed"] = True
    ctx.params["_healed_selector"] = healed_selector
    ctx.params["_original_selector"] = original
    return original
