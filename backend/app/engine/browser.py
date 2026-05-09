from __future__ import annotations
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

    @property
    def browser(self) -> Browser:
        if self._browser is None:
            raise RuntimeError("Browser not started.")
        return self._browser
