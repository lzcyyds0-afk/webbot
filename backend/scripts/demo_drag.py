#!/usr/bin/env python3
"""
Demo: drag & connect actions on React Flow example page.

Usage:
    cd backend
    PYTHONPATH=. uv run python scripts/demo_drag.py

This script:
1. Launches Chromium (non-headless)
2. Navigates to React Flow's basic example
3. Drags a node to a new position
4. Connects two node ports
5. Takes a final screenshot

TROUBLESHOOTING:
- If React Flow page doesn't load: check network, try a different URL
- If drag doesn't move the node: React Flow uses pointer events on the
  canvas; the node handle may need a more specific selector
- If connect fails: React Flow ports are small circles; use DevTools
  to find the exact selector for source/target handles
- If VLM check fails: set VLM_API_KEY env var or pass vlm_screenshot=false
"""
from __future__ import annotations
import asyncio
import sys

from playwright.async_api import async_playwright

# We test the low-level helpers directly (no DB needed for demo)
from app.engine.drag_and_connect import (
    _element_center,
    _wait_element_stable,
    _smooth_drag,
)


# ── React Flow example URLs ──
# The official React Flow examples are served at these URLs.
# REACT_FLOW_URL may change; if 404, try the alternative.
REACT_FLOW_URL = "https://reactflow.dev/examples/nodes/basic-node"
REACT_FLOW_ALT = "https://reactflow.dev/examples/interaction/drag-and-drop"


async def demo_reactflow() -> None:
    """Demo drag on React Flow basic example."""
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=False)
    ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
    page = await ctx.new_page()

    try:
        # ── Step 1: Navigate ──
        print("[1] Navigating to React Flow example...")
        await page.goto(REACT_FLOW_URL, wait_until="networkidle", timeout=30_000)
        await asyncio.sleep(2)  # let React hydrate

        # ── Step 2: Find a draggable node ──
        # React Flow nodes are typically .react-flow__node
        # The basic example has nodes with class "react-flow__node-default"
        node_selector = ".react-flow__node-default"
        try:
            await page.wait_for_selector(node_selector, timeout=10_000)
        except Exception:
            # Fallback: try any react-flow node
            node_selector = ".react-flow__node"
            await page.wait_for_selector(node_selector, timeout=10_000)

        nodes = await page.query_selector_all(node_selector)
        print(f"[2] Found {len(nodes)} nodes on canvas")

        if len(nodes) < 1:
            print("    No nodes found! Page may not have loaded correctly.")
            print("    Try opening the URL manually to verify:")
            print(f"    {REACT_FLOW_URL}")
            return

        # ── Step 3: Drag the first node 200px to the right ──
        print("[3] Dragging first node 200px to the right...")
        try:
            start_pos = await _wait_element_stable(page, node_selector)
            end_pos = {"x": start_pos["x"] + 200, "y": start_pos["y"]}
            print(f"    Start: ({start_pos['x']:.0f}, {start_pos['y']:.0f})")
            print(f"    End:   ({end_pos['x']:.0f}, {end_pos['y']:.0f})")
            await _smooth_drag(page, start_pos, end_pos, steps=20)
            await asyncio.sleep(0.5)
            print("    Drag completed!")
        except TimeoutError as e:
            print(f"    Element not stable: {e}")
            print("    TIP: Try adding a wait before drag, or use stable_frames=1")
        except Exception as e:
            print(f"    Drag failed: {e}")

        # ── Step 4: Try to connect two ports ──
        # React Flow handles (ports) are .react-flow__handle
        # Source handles: .react-flow__handle-bottom, .react-flow__handle-right
        # Target handles: .react-flow__handle-top, .react-flow__handle-left
        print("[4] Attempting to connect node ports...")
        source_handle = ".react-flow__handle-bottom"
        target_handle = ".react-flow__handle-top"

        try:
            src_count = len(await page.query_selector_all(source_handle))
            tgt_count = len(await page.query_selector_all(target_handle))
            print(f"    Source handles: {src_count}, Target handles: {tgt_count}")

            if src_count > 0 and tgt_count > 0:
                from_pos = await _wait_element_stable(page, source_handle)
                to_pos = await _wait_element_stable(page, target_handle)
                print(f"    From: ({from_pos['x']:.0f}, {from_pos['y']:.0f})")
                print(f"    To:   ({to_pos['x']:.0f}, {to_pos['y']:.0f})")
                await _smooth_drag(page, from_pos, to_pos, steps=20)
                await asyncio.sleep(0.5)
                print("    Connect completed!")
            else:
                print("    Not enough handles to connect")
                print("    TIP: Use DevTools to find handle selectors")
        except Exception as e:
            print(f"    Connect failed: {e}")
            print("    TIP: Handles may not be visible; scroll or zoom first")

        # ── Step 5: Final screenshot ──
        print("[5] Taking final screenshot...")
        await page.screenshot(path="storage/screenshots/demo_reactflow.png")
        print("    Saved to storage/screenshots/demo_reactflow.png")

    finally:
        await browser.close()
        await pw.stop()


async def demo_jsplumb() -> None:
    """Demo drag on jsPlumb community demo.

    jsPlumb uses HTML5 DnD or custom drag implementation.
    The official demo is at: https://jsplumbtoolkit.com/demo/flowchart
    """
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=False)
    ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
    page = await ctx.new_page()

    try:
        print("[1] Navigating to jsPlumb demo...")
        # jsPlumb's community demo page
        await page.goto(
            "https://jsplumbtoolkit.com/demo/flowchart",
            wait_until="networkidle",
            timeout=30_000,
        )
        await asyncio.sleep(3)

        # jsPlumb nodes are typically div.jtk-node
        node_selector = ".jtk-node, .w"
        try:
            await page.wait_for_selector(node_selector, timeout=10_000)
        except Exception:
            print("    jsPlumb nodes not found; page may require login or has changed")
            return

        nodes = await page.query_selector_all(node_selector)
        print(f"[2] Found {len(nodes)} nodes")

        if len(nodes) >= 1:
            print("[3] Dragging first node...")
            try:
                start_pos = await _wait_element_stable(page, node_selector)
                end_pos = {"x": start_pos["x"] + 150, "y": start_pos["y"] + 50}
                await _smooth_drag(page, start_pos, end_pos, steps=20)
                await asyncio.sleep(0.5)
                print("    Drag completed!")
            except Exception as e:
                print(f"    Drag failed: {e}")

        await page.screenshot(path="storage/screenshots/demo_jsplumb.png")
        print("[4] Saved to storage/screenshots/demo_jsplumb.png")

    finally:
        await browser.close()
        await pw.stop()


async def main() -> None:
    import os
    os.makedirs("storage/screenshots", exist_ok=True)

    print("=" * 60)
    print("WebBot Drag & Connect Demo")
    print("=" * 60)

    # Ensure Playwright browsers are installed
    print("\nChecking Playwright browsers...")
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "playwright", "install", "chromium",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()
    print("Chromium ready.")

    print("\n--- React Flow Demo ---")
    await demo_reactflow()

    print("\n--- jsPlumb Demo ---")
    await demo_jsplumb()

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
