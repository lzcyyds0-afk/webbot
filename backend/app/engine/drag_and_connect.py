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
    Consider using a shorter stable_frames=1 or adding a pre-wait.
    """
    deadline = time.monotonic() + timeout_ms / 1000
    prev_pos: dict | None = None
    stable_count = 0

    while time.monotonic() < deadline:
        pos = await _element_center(page, selector)
        if prev_pos and abs(pos["x"] - prev_pos["x"]) < 1 and abs(pos["y"] - prev_pos["y"]) < 1:
            stable_count += 1
            if stable_count >= stable_frames:
                return pos
        else:
            stable_count = 0
        prev_pos = pos
        await asyncio.sleep(interval_ms / 1000)

    raise TimeoutError(
        f"Element {selector!r} did not stabilize within {timeout_ms}ms"
    )


async def _smooth_drag(
    page: Page,
    start: dict,
    end: dict,
    *,
    steps: int = 20,
) -> None:
    """Smooth mouse drag from start to end.

    Moves the mouse in `steps` increments with 10-20ms sleep between
    each, simulating realistic human drag speed.

    PITFALL: Some canvas-based apps (e.g. ComfyUI) intercept pointer
    events at the canvas level and recalculate drop position from the
    pointer event stream. If steps is too low (< 10), the app may not
    register intermediate moves and the drop will be wrong.
    """
    await page.mouse.move(start["x"], start["y"])
    await page.mouse.down()

    for i in range(1, steps + 1):
        t = i / steps
        x = start["x"] + (end["x"] - start["x"]) * t
        y = start["y"] + (end["y"] - start["y"]) * t
        await page.mouse.move(x, y)
        # Random sleep 10-20ms to simulate human hand jitter
        await asyncio.sleep(random.uniform(0.010, 0.020))

    await page.mouse.up()


# ──────────────────────────────────────────────
#  drag action
# ──────────────────────────────────────────────

async def do_drag(page: Page, ctx: StepContext) -> StepResult:
    """Drag an element or move from a point to another point/element.

    Params:
        from_selector  (str)       - source element CSS selector
        to_selector    (str|None)  - target element CSS selector
        to_point       (dict|None) - target {x, y} in viewport coords
        steps          (int)       - interpolation steps (default 20)

    Either to_selector or to_point must be provided.

    COMMON FAILURE POINTS:
    1. Element not found -> check selector after page load, use wait first
    2. Element not stable -> increase timeout or add a wait action before
    3. Drop rejected by app -> canvas apps may need steps >= 30
    4. Viewport scroll -> if target is off-screen, drag coords are wrong;
       scroll the viewport first with a scroll action
    """
    from_sel = ctx.params.get("from_selector", "")
    to_sel = ctx.params.get("to_selector")
    to_point = ctx.params.get("to_point")
    steps = ctx.params.get("steps", 20)

    t0 = time.monotonic()
    try:
        # Wait for source element to be visible and stable
        start_pos = await _wait_element_stable(page, from_sel)

        # Determine end position
        if to_sel:
            end_pos = await _wait_element_stable(page, to_sel)
        elif to_point and "x" in to_point and "y" in to_point:
            end_pos = {"x": float(to_point["x"]), "y": float(to_point["y"])}
        else:
            raise ValueError("drag requires 'to_selector' or 'to_point'")

        await _smooth_drag(page, start_pos, end_pos, steps=steps)

        elapsed = int((time.monotonic() - t0) * 1000)
        return StepResult(
            step_index=ctx.step_index,
            action="drag",
            status=StepStatus.passed,
            duration_ms=elapsed,
            input_json={
                "from_selector": from_sel,
                "to_selector": to_sel,
                "to_point": to_point,
                "steps": steps,
            },
            output_json={
                "start": start_pos,
                "end": end_pos,
            },
            screenshot_path=None,
        )
    except (PwTimeout, TimeoutError, ValueError, Exception) as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        return StepResult(
            step_index=ctx.step_index,
            action="drag",
            status=StepStatus.failed,
            duration_ms=elapsed,
            input_json={
                "from_selector": from_sel,
                "to_selector": to_sel,
                "to_point": to_point,
                "steps": steps,
            },
            output_json=None,
            screenshot_path=None,
            error=str(exc),
        )


# ──────────────────────────────────────────────
#  connect action
# ──────────────────────────────────────────────

async def do_connect(page: Page, ctx: StepContext) -> StepResult:
    """Connect two ports on a visual node editor (e.g. Coze, n8n, React Flow).

    Params:
        from_port_selector (str)       - CSS selector for the source port/handle
        to_port_selector   (str)       - CSS selector for the target port/handle
        vlm_prompt         (str|None)  - custom VLM verification prompt
        vlm_screenshot     (bool)      - whether to do VLM check (default True)

    Flow:
    1. Wait for both ports to be stable
    2. Smooth drag from from_port center to to_port center
    3. Take screenshot
    4. Call assert_visual to confirm a connection line appeared

    COMMON FAILURE POINTS:
    1. Port selector wrong -> many node editors render ports as small
       circles/divs; use browser dev tools to find the exact selector
    2. Port not visible -> node may be off-screen; scroll first
    3. VLM false negative -> the connection line may be thin/overlapped;
       tune vlm_prompt or disable VLM check with vlm_screenshot=false
    4. Canvas-based rendering -> some apps (ComfyUI) draw connections on
       a <canvas>; DOM selectors won't work, use to_point instead
    5. Anti-duplicate check -> some apps reject a duplicate connection
       silently (no visual change); check if connection already exists
    """
    from_sel = ctx.params.get("from_port_selector", "")
    to_sel = ctx.params.get("to_port_selector", "")
    vlm_prompt = ctx.params.get(
        "vlm_prompt",
        "Is there a visible connection line or arrow between the two nodes/ports in this screenshot?",
    )
    do_vlm = ctx.params.get("vlm_screenshot", True)

    t0 = time.monotonic()
    try:
        # Wait for both ports to be stable
        from_pos = await _wait_element_stable(page, from_sel)
        to_pos = await _wait_element_stable(page, to_sel)

        # Smooth drag from source port to target port
        await _smooth_drag(page, from_pos, to_pos, steps=20)

        # Brief pause for the app to render the connection
        await asyncio.sleep(0.3)

        # Take verification screenshot
        storage = Storage()
        ss_path = storage.screenshot_path(ctx.run_id, ctx.step_index, suffix="_connect")
        await page.screenshot(path=str(ss_path), full_page=False)

        # VLM verification
        vlm_result = {"passed": True, "reason": "VLM check skipped"}
        if do_vlm:
            vlm_result = await assert_visual(
                str(ss_path),
                vlm_prompt,
            )

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
        return StepResult(
            step_index=ctx.step_index,
            action="connect",
            status=StepStatus.failed,
            duration_ms=elapsed,
            input_json={
                "from_port_selector": from_sel,
                "to_port_selector": to_sel,
            },
            output_json=None,
            screenshot_path=None,
            error=str(exc),
        )
