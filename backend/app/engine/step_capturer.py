"""Capture console logs, network requests, and DOM state for each step.

Uses Playwright's built-in event listeners (page.on) instead of raw CDP
for portability. Data is buffered per-step and flushed after the action
completes.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from playwright.async_api import Page

logger = logging.getLogger(__name__)


@dataclass
class StepCaptureData:
    console_logs: list[dict] = field(default_factory=list)
    network_requests: list[dict] = field(default_factory=list)
    dom_snippet: str | None = None
    target_bbox: dict | None = None

    def to_dict(self) -> dict:
        return {
            "console_logs": self.console_logs,
            "network_requests": self.network_requests,
            "dom_snippet": self.dom_snippet,
            "target_bbox": self.target_bbox,
        }


class StepCapturer:
    """Per-page capturer that buffers events per-step."""

    def __init__(self) -> None:
        self._page: Page | None = None
        self._active: bool = False
        self._console_logs: list[dict] = []
        self._network_requests: list[dict] = []
        self._dom_snippet: str | None = None
        self._target_bbox: dict | None = None

    # ── lifecycle ──

    async def setup(self, page: Page) -> None:
        """Attach listeners once per page."""
        self._page = page
        page.on("console", self._on_console)
        page.on("request", self._on_request)
        page.on("response", self._on_response)

    async def teardown(self) -> None:
        """Detach (best-effort) and clear."""
        self._active = False
        self._page = None
        self._console_logs.clear()
        self._network_requests.clear()

    # ── step boundaries ──

    def start_step(self) -> None:
        """Begin capturing for the current step."""
        self._active = True
        self._console_logs.clear()
        self._network_requests.clear()
        self._dom_snippet = None
        self._target_bbox = None

    def end_step(self) -> None:
        """Stop capturing for the current step."""
        self._active = False

    # ── target element capture ──

    async def capture_target(self, selector: str | None = None) -> None:
        """Extract DOM snippet and bounding box for the target element."""
        if not self._page or not selector:
            return

        # bbox
        try:
            locator = self._page.locator(selector).first
            bbox = await locator.bounding_box(timeout=5_000)
            if bbox:
                self._target_bbox = {
                    "x": round(bbox["x"]),
                    "y": round(bbox["y"]),
                    "width": round(bbox["width"]),
                    "height": round(bbox["height"]),
                }
        except Exception as exc:
            logger.debug("bbox capture failed for %s: %s", selector, exc)
            self._target_bbox = None

        # DOM snippet
        try:
            self._dom_snippet = await self._page.evaluate(
                """(selector) => {
                    const el = document.querySelector(selector);
                    if (!el) return null;
                    const parent = el.parentElement;
                    let html = el.outerHTML;
                    if (parent && parent.children.length > 1) {
                        const idx = Array.from(parent.children).indexOf(el);
                        const start = Math.max(0, idx - 1);
                        const end = Math.min(parent.children.length, idx + 2);
                        const siblings = Array.from(parent.children).slice(start, end);
                        html = siblings.map(c => c.outerHTML).join('\\n');
                    }
                    if (html.length > 4000) {
                        html = html.slice(0, 4000) + '\\n<!-- truncated -->';
                    }
                    return html;
                }""",
                selector,
            )
        except Exception as exc:
            logger.debug("DOM snippet capture failed for %s: %s", selector, exc)
            self._dom_snippet = None

    # ── data retrieval ──

    def get_data(self) -> StepCaptureData:
        """Return everything captured for the current step."""
        return StepCaptureData(
            console_logs=self._console_logs.copy(),
            network_requests=self._network_requests.copy(),
            dom_snippet=self._dom_snippet,
            target_bbox=self._target_bbox,
        )

    # ── event handlers ──

    def _on_console(self, msg) -> None:
        if not self._active:
            return
        try:
            text = msg.text
        except Exception:
            text = str(msg)
        self._console_logs.append({
            "type": msg.type,
            "text": text,
            "location": msg.location,
        })

    def _on_request(self, req) -> None:
        if not self._active:
            return
        entry = {
            "url": req.url,
            "method": req.method,
            "resource_type": req.resource_type,
            "headers": dict(req.headers),
        }
        self._network_requests.append(entry)

    def _on_response(self, resp) -> None:
        if not self._active:
            return
        # Pair with most recent unpaired request by URL
        matched = None
        for entry in reversed(self._network_requests):
            if entry["url"] == resp.url and "response" not in entry:
                matched = entry
                break

        resp_data = {
            "status": resp.status,
            "status_text": resp.status_text,
            "headers": dict(resp.headers),
        }

        if matched is not None:
            matched["response"] = resp_data
        else:
            # Orphan response — still record it
            self._network_requests.append({
                "url": resp.url,
                "method": resp.request.method if hasattr(resp, "request") else "?",
                "resource_type": resp.request.resource_type if hasattr(resp, "request") else "?",
                "response": resp_data,
            })


# ── persistence helpers ──

DETAILS_DIR = Path("storage/runs")


def details_path(run_id: int, step_index: int) -> Path:
    path = DETAILS_DIR / str(run_id) / str(step_index)
    path.mkdir(parents=True, exist_ok=True)
    return path / "details.json"


def persist_step_details(run_id: int, step_index: int, data: StepCaptureData) -> None:
    """Write step capture data to disk."""
    path = details_path(run_id, step_index)
    try:
        path.write_text(json.dumps(data.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        logger.exception("Failed to persist step details for run=%s step=%s", run_id, step_index)


def load_step_details(run_id: int, step_index: int) -> StepCaptureData | None:
    """Read step capture data from disk."""
    path = details_path(run_id, step_index)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return StepCaptureData(
            console_logs=raw.get("console_logs", []),
            network_requests=raw.get("network_requests", []),
            dom_snippet=raw.get("dom_snippet"),
            target_bbox=raw.get("target_bbox"),
        )
    except Exception:
        logger.exception("Failed to load step details for run=%s step=%s", run_id, step_index)
        return None
