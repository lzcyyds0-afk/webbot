"""Login / authentication helpers for the action executor.

Provides:
- `do_login`: a DSL action that fills a username/password form and verifies success.
- `is_likely_login_page`: heuristic to detect a redirect-to-login.
- `inject_storage_state`: write localStorage / sessionStorage entries before navigation.
"""
from __future__ import annotations

import logging
import time
from urllib.parse import urlparse

from playwright.async_api import Page, TimeoutError as PwTimeout

from app.engine.models import StepContext, StepResult
from app.models.run_step import StepStatus

logger = logging.getLogger(__name__)


# Common URL patterns / DOM hints that suggest a login page
_LOGIN_URL_PATTERNS = ("login", "signin", "sign-in", "auth", "passport", "account")
_LOGIN_DOM_SELECTORS = (
    'input[type="password"]',
    'form[action*="login" i]',
    'form[action*="signin" i]',
    '[data-testid*="login" i]',
)


async def is_likely_login_page(page: Page) -> dict:
    """Return {'is_login': bool, 'reason': str, 'url': str}.

    Lightweight, never throws.
    """
    info = {"is_login": False, "reason": "", "url": ""}
    try:
        url = page.url or ""
        info["url"] = url
        path = urlparse(url).path.lower()
        for pat in _LOGIN_URL_PATTERNS:
            if pat in path:
                info["is_login"] = True
                info["reason"] = f"URL path contains '{pat}'"
                return info

        # DOM-based hints
        for sel in _LOGIN_DOM_SELECTORS:
            try:
                count = await page.locator(sel).count()
                if count > 0:
                    info["is_login"] = True
                    info["reason"] = f"page has selector '{sel}'"
                    return info
            except Exception:
                continue
    except Exception as exc:
        info["reason"] = f"detection error: {exc}"
    return info


async def inject_storage_state(
    page: Page,
    local_storage: dict | None = None,
    session_storage: dict | None = None,
) -> None:
    """Write entries to window.localStorage / sessionStorage.

    Call AFTER the first navigation (storage is per-origin, requires a loaded page).
    """
    if not local_storage and not session_storage:
        return
    payload = {
        "local": local_storage or {},
        "session": session_storage or {},
    }
    js = """
    ({local, session}) => {
        for (const [k, v] of Object.entries(local || {})) {
            try { window.localStorage.setItem(k, v); } catch (e) {}
        }
        for (const [k, v] of Object.entries(session || {})) {
            try { window.sessionStorage.setItem(k, v); } catch (e) {}
        }
    }
    """
    try:
        await page.evaluate(js, payload)
    except Exception as exc:
        logger.warning("Failed to inject storage state: %s", exc)


async def do_login(page: Page, ctx: StepContext) -> StepResult:
    """Fill a username/password form and submit, verify navigation.

    Params:
        url                 (str, optional) - login page URL; if provided, navigates first.
                                              If omitted, assumes current page is login.
        username            (str, required) - text to fill in username field.
        password            (str, required) - text to fill in password field.
        username_selector   (str, optional) - CSS selector; default tries common patterns.
        password_selector   (str, optional) - CSS selector; default tries common patterns.
        submit_selector     (str, optional) - CSS selector for the submit button;
                                              default tries common patterns.
        success_url_pattern (str, optional) - regex; if URL matches after submit, success.
        success_selector    (str, optional) - if this selector appears, success.
        timeout_ms          (int, optional) - max wait for success (default 15000).

    Verification:
        After submit, login is considered successful if EITHER:
        - URL changes to one that no longer looks like a login page, OR
        - `success_selector` becomes visible, OR
        - `success_url_pattern` matches the URL.

    PITFALLS:
    1. MFA / CAPTCHA — this step will fail; tests must bypass via cookies/credentials.
    2. CSRF tokens — usually handled by the form itself, but some sites require a delay.
    3. Async login (XHR submit) — relies on `success_*` checks, not navigation.
    """
    import re

    url = ctx.params.get("url")
    username = ctx.params.get("username") or ""
    password = ctx.params.get("password") or ""
    username_sel = ctx.params.get("username_selector")
    password_sel = ctx.params.get("password_selector")
    submit_sel = ctx.params.get("submit_selector")
    success_url_re = ctx.params.get("success_url_pattern")
    success_sel = ctx.params.get("success_selector")
    timeout_ms = int(ctx.params.get("timeout_ms", 15_000))

    t0 = time.monotonic()
    try:
        if not username or not password:
            raise ValueError("login requires both 'username' and 'password'")

        # ── Navigate to login page (optional) ──
        if url:
            target = url
            if target and not target.startswith(("http://", "https://")):
                target = ctx.base_url.rstrip("/") + "/" + target.lstrip("/")
            await page.goto(target, wait_until="domcontentloaded", timeout=timeout_ms)

        # ── Resolve username field ──
        user_loc = await _resolve_input(
            page,
            user_sel=username_sel,
            candidates=(
                'input[type="email"]',
                'input[name*="user" i]',
                'input[name*="email" i]',
                'input[name*="account" i]',
                'input[id*="user" i]',
                'input[id*="email" i]',
                'input[autocomplete="username"]',
            ),
        )
        if user_loc is None:
            raise ValueError("Could not locate username field (provide 'username_selector')")
        await user_loc.fill(username, timeout=timeout_ms)

        # ── Resolve password field ──
        pwd_loc = await _resolve_input(
            page,
            user_sel=password_sel,
            candidates=(
                'input[type="password"]',
                'input[name*="pass" i]',
                'input[id*="pass" i]',
                'input[autocomplete="current-password"]',
            ),
        )
        if pwd_loc is None:
            raise ValueError("Could not locate password field (provide 'password_selector')")
        await pwd_loc.fill(password, timeout=timeout_ms)

        # ── Resolve submit button ──
        submit_loc = await _resolve_input(
            page,
            user_sel=submit_sel,
            candidates=(
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("登录")',
                'button:has-text("登陆")',
                'button:has-text("Log in")',
                'button:has-text("Login")',
                'button:has-text("Sign in")',
            ),
        )

        # Click submit and wait for either a navigation OR a success signal.
        before_url = page.url
        if submit_loc is not None:
            try:
                async with page.expect_navigation(timeout=timeout_ms, wait_until="domcontentloaded"):
                    await submit_loc.click(timeout=timeout_ms)
            except Exception:
                # No navigation fired — XHR login, fall through to success checks
                pass
        else:
            # No submit button — try pressing Enter on password field
            await pwd_loc.press("Enter")

        # ── Verify success ──
        success = False
        reason = ""
        deadline = time.monotonic() + (timeout_ms / 1000)
        while time.monotonic() < deadline:
            cur_url = page.url
            if success_url_re and re.search(success_url_re, cur_url):
                success = True
                reason = f"URL matches success_url_pattern: {cur_url}"
                break
            if success_sel:
                try:
                    if await page.locator(success_sel).first.is_visible():
                        success = True
                        reason = f"success_selector visible: {success_sel}"
                        break
                except Exception:
                    pass
            # Default: not a login page anymore
            check = await is_likely_login_page(page)
            if not check["is_login"] and cur_url != before_url:
                success = True
                reason = f"navigated away from login page to {cur_url}"
                break
            import asyncio
            await asyncio.sleep(0.3)

        elapsed = int((time.monotonic() - t0) * 1000)
        if not success:
            return StepResult(
                step_index=ctx.step_index,
                action="login",
                status=StepStatus.failed,
                duration_ms=elapsed,
                input_json={"url": url, "username": _mask(username)},
                output_json={"current_url": page.url, "reason": "no success signal within timeout"},
                screenshot_path=None,
                error="Login did not produce a success signal within timeout",
            )

        return StepResult(
            step_index=ctx.step_index,
            action="login",
            status=StepStatus.passed,
            duration_ms=elapsed,
            input_json={"url": url, "username": _mask(username)},
            output_json={"current_url": page.url, "reason": reason},
            screenshot_path=None,
        )

    except (PwTimeout, ValueError, Exception) as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        return StepResult(
            step_index=ctx.step_index,
            action="login",
            status=StepStatus.failed,
            duration_ms=elapsed,
            input_json={"url": url, "username": _mask(username)},
            output_json={"current_url": page.url},
            screenshot_path=None,
            error=str(exc),
        )


# ── Internal helpers ──

async def _resolve_input(page: Page, *, user_sel: str | None, candidates: tuple[str, ...]):
    """Return the first visible Locator from user_sel or the candidates list."""
    if user_sel:
        try:
            loc = page.locator(user_sel).first
            if await loc.is_visible():
                return loc
        except Exception:
            return None
        return None

    for sel in candidates:
        try:
            loc = page.locator(sel).first
            if await loc.count() and await loc.is_visible():
                return loc
        except Exception:
            continue
    return None


def _mask(value: str) -> str:
    """Mask sensitive value for logging — show first 2 chars only."""
    if not value:
        return ""
    if len(value) <= 2:
        return "**"
    return value[:2] + "***"
