from __future__ import annotations
import asyncio
from pathlib import Path
from playwright.async_api import Page


class Storage:
    BASE_DIR = Path("storage/screenshots")

    def screenshot_path(
        self, run_id: int, step_index: int, suffix: str = ""
    ) -> Path:
        dir_path = self.BASE_DIR / str(run_id)
        dir_path.mkdir(parents=True, exist_ok=True)
        filename = f"{step_index}{suffix}.png"
        return dir_path / filename

    async def save_screenshot(
        self, page: Page, path: Path, full_page: bool = False
    ) -> str:
        await page.screenshot(path=str(path), full_page=full_page)
        return str(path)
