from __future__ import annotations
import asyncio
import logging
import random
import time

from playwright.async_api import Page, TimeoutError as PwTimeout

from app.engine.models import StepContext, StepResult
from app.engine.vlm import assert_visual
from app.engine.storage import Storage
from app.models.run_step import StepStatus

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────

async def _element_center(page: Page, selector: str) -> dict:
    """Get the center {x, y} of the first element matching selector."""
    box = await page.evaluate(
        """(selector) => {
            const el = document.querySelector(selector);
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
        }""",
        selector,
    )
    if box is None:
        raise ValueError(f"Element not found: {selector}")
    return box


async def _element_bbox(page: Page, selector: str) -> dict | None:
    """Return the full bounding rect for diagnostics."""
    return await page.evaluate(
        """(selector) => {
            const el = document.querySelector(selector);
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return { x: r.left, y: r.top, w: r.width, h: r.height };
        }""",
        selector,
    )


async def _scroll_into_view(page: Page, selector: str, timeout_ms: int = 5_000) -> None:
    """Scroll the matched element into view; silently ignore if not found."""
    try:
        loc = page.locator(selector).first
        await loc.scroll_into_view_if_needed(timeout=timeout_ms)
    except Exception as exc:
        logger.debug("scroll_into_view skipped for %s: %s", selector, exc)


async def _wait_element_stable(
    page: Page,
    selector: str,
    *,
    stable_frames: int = 2,
    interval_ms: int = 100,
    timeout_ms: int = 5_000,
) -> dict:
    """Wait until the element's center position is stable for N frames.

    PITFALL: If the element is inside a scrolling container that is
    still animating (e.g. auto-scroll on drag), this may never stabilize.
    """
    deadline = time.monotonic() + timeout_ms / 1000
    prev_pos: dict | None = None
    stable_count = 0
    last_error: str = ""

    while time.monotonic() < deadline:
        try:
            pos = await _element_center(page, selector)
        except ValueError as exc:
            last_error = str(exc)
            await asyncio.sleep(interval_ms / 1000)
            continue
        if prev_pos and abs(pos["x"] - prev_pos["x"]) < 1 and abs(pos["y"] - prev_pos["y"]) < 1:
            stable_count += 1
            if stable_count >= stable_frames:
                return pos
        else:
            stable_count = 0
        prev_pos = pos
        await asyncio.sleep(interval_ms / 1000)

    if last_error:
        raise TimeoutError(
            f"Element {selector!r} not stable / not found within {timeout_ms}ms ({last_error})"
        )
    raise TimeoutError(
        f"Element {selector!r} did not stabilize within {timeout_ms}ms"
    )


def _apply_offset(pos: dict, offset: dict | None) -> dict:
    """Apply optional {dx, dy} offset to a position dict."""
    if not offset:
        return pos
    return {
        "x": pos["x"] + float(offset.get("dx", 0)),
        "y": pos["y"] + float(offset.get("dy", 0)),
    }


async def _smooth_drag(
    page: Page,
    start: dict,
    end: dict,
    *,
    steps: int = 20,
    hold_ms: int = 0,
) -> None:
    """Smooth mouse drag from start to end.

    `hold_ms`: optional pause after mouse-down before moving (for apps that
    require long-press to initiate a drag, e.g. sortable lists).

    PITFALL: Some canvas-based apps (e.g. ComfyUI) intercept pointer events
    at the canvas level. If steps is too low (< 10), the app may not register
    intermediate moves and the drop will be wrong.
    """
    await page.mouse.move(start["x"], start["y"])
    await page.mouse.down()

    if hold_ms > 0:
        await asyncio.sleep(hold_ms / 1000)

    for i in range(1, steps + 1):
        t = i / steps
        x = start["x"] + (end["x"] - start["x"]) * t
        y = start["y"] + (end["y"] - start["y"]) * t
        await page.mouse.move(x, y)
        # Random sleep 10-20ms to simulate human hand jitter
        await asyncio.sleep(random.uniform(0.010, 0.020))

    await page.mouse.up()


async def _html5_drag(
    page: Page,
    from_selector: str,
    to_selector: str | None,
    to_point: dict | None,
) -> None:
    """Dispatch HTML5 native drag-and-drop events.

    For apps that use the HTML5 DnD API (`dragstart`/`dragover`/`drop`),
    pure mouse drag often does NOT trigger the drop handler — the browser
    only fires native DnD events when interacting with `draggable=true`
    elements through real input pipeline. This helper synthesizes those
    events at the DOM level, which works for most React DnD / native HTML5
    cases.

    NOTE: This bypasses some pointerdown/up animations. Use mouse mode if
    the app relies on transitional visual feedback (ghost image, etc.).
    """
    if not to_selector and not to_point:
        raise ValueError("html5 drag requires to_selector or to_point")

    js = """
    async ({fromSel, toSel, toPoint}) => {
        const src = document.querySelector(fromSel);
        if (!src) throw new Error('Source element not found: ' + fromSel);

        let target, x, y;
        if (toSel) {
            target = document.querySelector(toSel);
            if (!target) throw new Error('Target element not found: ' + toSel);
            const r = target.getBoundingClientRect();
            x = r.left + r.width / 2;
            y = r.top + r.height / 2;
        } else {
            target = document.elementFromPoint(toPoint.x, toPoint.y) || document.body;
            x = toPoint.x;
            y = toPoint.y;
        }

        const dt = new DataTransfer();
        const fire = (el, type, clientX, clientY) => {
            const ev = new DragEvent(type, {
                bubbles: true,
                cancelable: true,
                composed: true,
                clientX, clientY,
                dataTransfer: dt,
            });
            el.dispatchEvent(ev);
        };

        const sr = src.getBoundingClientRect();
        const sx = sr.left + sr.width / 2;
        const sy = sr.top + sr.height / 2;

        fire(src, 'dragstart', sx, sy);
        fire(target, 'dragenter', x, y);
        fire(target, 'dragover', x, y);
        fire(target, 'drop', x, y);
        fire(src, 'dragend', x, y);
        return true;
    }
    """
    await page.evaluate(js, {
        "fromSel": from_selector,
        "toSel": to_selector,
        "toPoint": to_point,
    })


# ──────────────────────────────────────────────
#  drag action
# ──────────────────────────────────────────────

async def do_drag(page: Page, ctx: StepContext) -> StepResult:
    """Drag an element / point to another point or element.

    Params:
        from_selector  (str|None)  - source element CSS selector
        from_point     (dict|None) - source {x, y} coordinates (alternative to from_selector)
        to_selector    (str|None)  - target element CSS selector
        to_point       (dict|None) - target {x, y} in viewport coords
        offset         (dict|None) - {dx, dy} added to the target position
        steps          (int)       - interpolation steps (default 20)
        hold_ms        (int)       - mouse-down hold before moving (default 0)
        mode           (str)       - "mouse" (default) | "html5" — choose the
                                     drag implementation. Use "html5" when the
                                     app relies on native HTML5 DnD events and
                                     mouse-level drag has no effect.
        scroll         (bool)      - auto scroll source/target into view first
                                     (default True)

    COMMON FAILURE POINTS:
    1. Element not found -> add a wait step first
    2. Drop rejected by app -> raise `steps` to 30+ for canvas apps
    3. HTML5 DnD apps -> set mode="html5"
    4. Long-press to activate (e.g. sortable.js) -> set hold_ms=300
    5. Target off-screen -> scroll defaults to True; set False to disable
    """
    from_sel = ctx.params.get("from_selector") or ""
    from_point = ctx.params.get("from_point")
    to_sel = ctx.params.get("to_selector")
    to_point = ctx.params.get("to_point")
    offset = ctx.params.get("offset")
    steps = int(ctx.params.get("steps", 20))
    hold_ms = int(ctx.params.get("hold_ms", 0))
    mode = ctx.params.get("mode", "mouse")
    scroll = bool(ctx.params.get("scroll", True))

    t0 = time.monotonic()
    try:
        # ── Source position ──
        if from_sel:
            if scroll:
                await _scroll_into_view(page, from_sel)
            start_pos = await _wait_element_stable(page, from_sel)
        elif from_point and "x" in from_point and "y" in from_point:
            start_pos = {"x": float(from_point["x"]), "y": float(from_point["y"])}
        else:
            raise ValueError("drag requires 'from_selector' or 'from_point'")

        # ── Target position ──
        if to_sel:
            if scroll:
                await _scroll_into_view(page, to_sel)
            end_pos = await _wait_element_stable(page, to_sel)
        elif to_point and "x" in to_point and "y" in to_point:
            end_pos = {"x": float(to_point["x"]), "y": float(to_point["y"])}
        else:
            raise ValueError("drag requires 'to_selector' or 'to_point'")

        end_pos = _apply_offset(end_pos, offset)

        # ── Execute drag ──
        if mode == "html5":
            if not from_sel:
                raise ValueError("html5 mode requires from_selector")
            await _html5_drag(page, from_sel, to_sel, end_pos if not to_sel else None)
        else:
            await _smooth_drag(page, start_pos, end_pos, steps=steps, hold_ms=hold_ms)

        elapsed = int((time.monotonic() - t0) * 1000)
        return StepResult(
            step_index=ctx.step_index,
            action="drag",
            status=StepStatus.passed,
            duration_ms=elapsed,
            input_json={
                "from_selector": from_sel,
                "from_point": from_point,
                "to_selector": to_sel,
                "to_point": to_point,
                "offset": offset,
                "steps": steps,
                "hold_ms": hold_ms,
                "mode": mode,
            },
            output_json={
                "start": start_pos,
                "end": end_pos,
                "mode": mode,
            },
            screenshot_path=None,
        )
    except (PwTimeout, TimeoutError, ValueError, Exception) as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        # Collect diagnostic bbox info on failure
        diag = {}
        try:
            if from_sel:
                diag["from_bbox"] = await _element_bbox(page, from_sel)
            if to_sel:
                diag["to_bbox"] = await _element_bbox(page, to_sel)
        except Exception:
            pass
        return StepResult(
            step_index=ctx.step_index,
            action="drag",
            status=StepStatus.failed,
            duration_ms=elapsed,
            input_json={
                "from_selector": from_sel,
                "from_point": from_point,
                "to_selector": to_sel,
                "to_point": to_point,
                "offset": offset,
                "steps": steps,
                "hold_ms": hold_ms,
                "mode": mode,
            },
            output_json=diag or None,
            screenshot_path=None,
            error=str(exc),
        )


# ──────────────────────────────────────────────
#  connect action
# ──────────────────────────────────────────────

async def do_connect(page: Page, ctx: StepContext) -> StepResult:
    """Connect two ports on a visual node editor (Coze / n8n / React Flow / ComfyUI).

    Params:
        from_port_selector (str)       - CSS selector for the source port
        to_port_selector   (str)       - CSS selector for the target port
        to_point           (dict|None) - alternative target point (for canvas apps)
        offset             (dict|None) - {dx, dy} added to target position
        steps              (int)       - interpolation steps (default 20)
        hold_ms            (int)       - mouse-down hold (default 0)
        mode               (str)       - "mouse" (default) | "html5"
        scroll             (bool)      - auto scroll ports into view (default True)
        vlm_prompt         (str|None)  - custom VLM verification prompt
        vlm_screenshot     (bool)      - whether to do VLM check (default True)
    """
    from_sel = ctx.params.get("from_port_selector", "")
    to_sel = ctx.params.get("to_port_selector", "")
    to_point = ctx.params.get("to_point")
    offset = ctx.params.get("offset")
    steps = int(ctx.params.get("steps", 20))
    hold_ms = int(ctx.params.get("hold_ms", 0))
    mode = ctx.params.get("mode", "mouse")
    scroll = bool(ctx.params.get("scroll", True))
    vlm_prompt = ctx.params.get(
        "vlm_prompt",
        "Is there a visible connection line or arrow between the two nodes/ports in this screenshot?",
    )
    do_vlm = ctx.params.get("vlm_screenshot", True)

    t0 = time.monotonic()
    try:
        # ── Source port ──
        if scroll and from_sel:
            await _scroll_into_view(page, from_sel)
        from_pos = await _wait_element_stable(page, from_sel)

        # ── Target port / point ──
        if to_sel:
            if scroll:
                await _scroll_into_view(page, to_sel)
            to_pos = await _wait_element_stable(page, to_sel)
        elif to_point and "x" in to_point and "y" in to_point:
            to_pos = {"x": float(to_point["x"]), "y": float(to_point["y"])}
        else:
            raise ValueError("connect requires 'to_port_selector' or 'to_point'")

        to_pos = _apply_offset(to_pos, offset)

        # ── Execute drag ──
        if mode == "html5":
            await _html5_drag(page, from_sel, to_sel, to_pos if not to_sel else None)
        else:
            await _smooth_drag(page, from_pos, to_pos, steps=steps, hold_ms=hold_ms)

        # Brief pause for the app to render the connection
        await asyncio.sleep(0.3)

        # Take verification screenshot
        storage = Storage()
        ss_path = storage.screenshot_path(ctx.run_id, ctx.step_index, suffix="_connect")
        await page.screenshot(path=str(ss_path), full_page=False)

        # VLM verification
        vlm_result = {"passed": True, "reason": "VLM check skipped"}
        if do_vlm:
            vlm_result = await assert_visual(str(ss_path), vlm_prompt)

        elapsed = int((time.monotonic() - t0) * 1000)

        if not vlm_result["passed"]:
            return StepResult(
                step_index=ctx.step_index,
                action="connect",
                status=StepStatus.failed,
                duration_ms=elapsed,
                input_json={
                    "from_port_selector": from_sel,
                    "to_port_selector": to_sel,
                    "to_point": to_point,
                    "offset": offset,
                    "mode": mode,
                },
                output_json={
                    "from_pos": from_pos,
                    "to_pos": to_pos,
                    "vlm": vlm_result,
                },
                screenshot_path=str(ss_path),
                error=f"VLM verification failed: {vlm_result['reason']}",
            )

        return StepResult(
            step_index=ctx.step_index,
            action="connect",
            status=StepStatus.passed,
            duration_ms=elapsed,
            input_json={
                "from_port_selector": from_sel,
                "to_port_selector": to_sel,
                "to_point": to_point,
                "offset": offset,
                "mode": mode,
            },
            output_json={
                "from_pos": from_pos,
                "to_pos": to_pos,
                "vlm": vlm_result,
            },
            screenshot_path=str(ss_path),
        )

    except (PwTimeout, TimeoutError, ValueError, Exception) as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        diag = {}
        try:
            if from_sel:
                diag["from_bbox"] = await _element_bbox(page, from_sel)
            if to_sel:
                diag["to_bbox"] = await _element_bbox(page, to_sel)
        except Exception:
            pass
        return StepResult(
            step_index=ctx.step_index,
            action="connect",
            status=StepStatus.failed,
            duration_ms=elapsed,
            input_json={
                "from_port_selector": from_sel,
                "to_port_selector": to_sel,
                "to_point": to_point,
                "offset": offset,
                "mode": mode,
            },
            output_json=diag or None,
            screenshot_path=None,
            error=str(exc),
        )
