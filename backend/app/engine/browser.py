from __future__ import annotations
import asyncio
from playwright.async_api import async_playwright, Browser, Page, Playwright
from app.core.config import settings


class BrowserManager:
    def __init__(
        self,
        headless: bool | None = None,
        viewport_width: int = 1440,
        viewport_height: int = 900,
    ) -> None:
        self._headless = headless if headless is not None else settings.headless
        self._viewport = {"width": viewport_width, "height": viewport_height}
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        # Prefer system-installed Google Chrome (lighter, avoids extra download).
        # Fallback to bundled Chromium on Windows if Chrome is not installed.
        try:
            self._browser = await self._playwright.chromium.launch(
                headless=self._headless,
                channel="chrome",
            )
        except Exception:
            self._browser = await self._playwright.chromium.launch(
                headless=self._headless,
            )

    async def new_page(self, cookies: list[dict] | None = None) -> Page:
        if self._browser is None:
            raise RuntimeError("Browser not started. Call start() first.")
        context = await self._browser.new_context(
            viewport=self._viewport,
        )
        if cookies:
            try:
                await context.add_cookies(cookies)
            except Exception:
                logger = __import__("logging").getLogger(__name__)
                logger.warning("Failed to add cookies, continuing without them")
        return await context.new_page()

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._browser = None
        self._playwright = None

    def is_alive(self) -> bool:
        return self._browser is not None and self._browser.is_connected()

    @property
    def browser(self) -> Browser:
        if self._browser is None:
            raise RuntimeError("Browser not started.")
        return self._browser


# ── Process-wide shared browser ──
#
# Launching a Chromium process per run is the dominant per-run cost. Instead we
# keep one browser alive for the whole process and give each run its own browser
# *context* (cookies/storage stay isolated). The launch is lazy and guarded by a
# lock so concurrent first-runs don't race to launch twice.

_shared: BrowserManager | None = None
_shared_lock = asyncio.Lock()


async def get_shared_browser() -> BrowserManager:
    """Return the shared, started BrowserManager, launching (or relaunching a
    crashed one) on demand."""
    global _shared
    if _shared is not None and _shared.is_alive():
        return _shared
    async with _shared_lock:
        # Re-check inside the lock: another coroutine may have launched it.
        if _shared is None or not _shared.is_alive():
            mgr = BrowserManager()
            await mgr.start()
            _shared = mgr
    return _shared


async def shutdown_shared_browser() -> None:
    """Close the shared browser on application shutdown."""
    global _shared
    if _shared is not None:
        await _shared.close()
        _shared = None
