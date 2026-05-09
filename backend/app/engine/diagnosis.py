"""Failed-step diagnosis generator.

Analyzes DOM state, viewport, network, and historical runs to produce
a structured diagnosis payload consumed by the frontend drawer.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import Page
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.models import StepContext, StepResult
from app.engine.step_capturer import StepCaptureData
from app.models.run import Run, RunStatus
from app.models.run_step import RunStep, StepStatus
from app.models.step_diagnosis import StepDiagnosis

logger = logging.getLogger(__name__)

# ── Error type classification ──

def _classify_error(error_text: str | None) -> str:
    if not error_text:
        return "UnknownError"
    lower = error_text.lower()
    if "timeout" in lower:
        return "TimeoutError"
    if "selector" in lower or "locator" in lower:
        return "SelectorError"
    if "navigation" in lower or "goto" in lower:
        return "NavigationError"
    if "visible" in lower:
        return "VisibilityError"
    if "detached" in lower or "stale" in lower:
        return "StaleElementError"
    return "ExecutionError"


# ── DOM probing ──

async def _probe_selector(page: Page, selector: str | None) -> dict[str, Any]:
    """Check if selector exists, is visible, and whether it's obscured."""
    result = {
        "exists": False,
        "visible": False,
        "obscured": False,
        "bbox": None,
        "center_element": None,
    }
    if not selector:
        return result

    try:
        count = await page.locator(selector).count()
        result["exists"] = count > 0
        if count == 0:
            return result

        locator = page.locator(selector).first
        result["visible"] = await locator.is_visible(timeout=3_000)

        bbox = await locator.bounding_box(timeout=3_000)
        if bbox:
            result["bbox"] = {
                "x": round(bbox["x"]),
                "y": round(bbox["y"]),
                "width": round(bbox["width"]),
                "height": round(bbox["height"]),
            }
            # Check if element at center point equals target
            cx = bbox["x"] + bbox["width"] / 2
            cy = bbox["y"] + bbox["height"] / 2
            center_el = await page.evaluate(
                """([x, y]) => {
                    const el = document.elementFromPoint(x, y);
                    return el ? el.tagName + (el.id ? '#' + el.id : '') + (el.className ? '.' + el.className.split(/\\s+/).slice(0,2).join('.') : '') : null;
                }""",
                [cx, cy],
            )
            result["center_element"] = center_el
            # Simple obscured check: if elementFromPoint doesn't return something
            # that contains our target selector, it might be obscured
            target_el = await page.evaluate(
                """(selector) => {
                    const el = document.querySelector(selector);
                    return el ? el.outerHTML.slice(0, 200) : null;
                }""",
                selector,
            )
            result["obscured"] = center_el is None or (
                target_el and center_el not in target_el
            )
    except Exception as exc:
        logger.debug("DOM probe failed for %s: %s", selector, exc)

    return result


# ── Viewport info ──

async def _get_viewport_info(page: Page) -> dict[str, Any]:
    return await page.evaluate("""() => {
        return {
            width: window.innerWidth,
            height: window.innerHeight,
            scroll_x: window.scrollX,
            scroll_y: window.scrollY,
        };
    }""")


# ── Candidate selector search ──

async def _find_candidate_selectors(page: Page, target_selector: str | None) -> list[dict]:
    """Search DOM for elements similar to the failed target."""
    if not target_selector:
        return []

    candidates = []
    try:
        # Get target element properties
        target_info = await page.evaluate(
            """(selector) => {
                const el = document.querySelector(selector);
                if (!el) return null;
                return {
                    tag: el.tagName.toLowerCase(),
                    text: (el.textContent || '').trim().slice(0, 60),
                    type: el.type || null,
                    role: el.getAttribute('role') || null,
                    aria_label: el.getAttribute('aria-label') || null,
                };
            }""",
            target_selector,
        )
        if not target_info:
            return candidates

        # Search by tag + text similarity
        similar = await page.evaluate(
            """(target) => {
                const results = [];
                const all = document.querySelectorAll(target.tag);
                for (const el of all) {
                    const text = (el.textContent || '').trim().slice(0, 60);
                    const type = el.type || null;
                    const role = el.getAttribute('role') || null;
                    const aria = el.getAttribute('aria-label') || null;
                    let score = 0;
                    if (type === target.type) score += 0.3;
                    if (role === target.role) score += 0.3;
                    if (aria && aria === target.aria_label) score += 0.3;
                    if (text && target.text) {
                        if (text === target.text) score += 0.4;
                        else if (text.includes(target.text) || target.text.includes(text)) score += 0.2;
                    }
                    if (score > 0.3) {
                        let sel = '';
                        if (el.id) sel = '#' + CSS.escape(el.id);
                        else if (el.getAttribute('data-testid')) sel = `[data-testid="${el.getAttribute('data-testid')}"]`;
                        else if (aria) sel = `${target.tag}[aria-label="${aria}"]`;
                        else if (text && text.length <= 40) sel = `${target.tag}:has-text("${text.replace(/"/g, '\\"')}")`;
                        else sel = target.tag + (el.className ? '.' + el.className.trim().split(/\\s+/).filter(c => !c.startsWith('bg-') && !c.startsWith('text-') && !c.startsWith('p-') && !c.startsWith('m-')).slice(0,2).join('.') : '');
                        results.push({ selector: sel, score: Math.min(score, 0.99), text: text.slice(0, 40) });
                    }
                }
                // Deduplicate by selector
                const seen = new Set();
                return results.filter(r => { if (seen.has(r.selector)) return false; seen.add(r.selector); return true; });
            }""",
            target_info,
        )

        for item in similar[:5]:
            if item["selector"] == target_selector:
                continue
            try:
                count = await page.locator(item["selector"]).count()
            except Exception:
                count = 0
            candidates.append({
                "selector": item["selector"],
                "confidence": round(item["score"], 2),
                "reason": f"同 tag({target_info['tag']})" + (f" + 相似文本\"{item['text']}\"" if item["text"] else ""),
                "found_count": count,
            })
    except Exception as exc:
        logger.debug("Candidate selector search failed: %s", exc)

    return candidates


# ── Baseline lookup ──

async def _find_baseline_screenshot(
    db: AsyncSession, run_id: int, step_index: int
) -> dict[str, Any] | None:
    """Find the most recent passed run for the same test case with a screenshot for this step."""
    try:
        # Get current run's test_case_id
        run_result = await db.execute(select(Run).where(Run.id == run_id))
        run = run_result.scalar_one_or_none()
        if not run:
            return None

        # Find most recent passed run for same test case, excluding current
        baseline_run_result = await db.execute(
            select(Run)
            .where(
                Run.test_case_id == run.test_case_id,
                Run.status == RunStatus.passed,
                Run.id != run_id,
            )
            .order_by(Run.started_at.desc())
            .limit(1)
        )
        baseline_run = baseline_run_result.scalar_one_or_none()
        if not baseline_run:
            return None

        # Find the corresponding step
        baseline_step_result = await db.execute(
            select(RunStep)
            .where(
                RunStep.run_id == baseline_run.id,
                RunStep.step_index == step_index,
            )
        )
        baseline_step = baseline_step_result.scalar_one_or_none()
        if not baseline_step or not baseline_step.screenshot_path:
            return None

        return {
            "run_id": baseline_run.id,
            "screenshot_url": baseline_step.screenshot_path,
            "run_started_at": baseline_run.started_at.isoformat() if baseline_run.started_at else None,
        }
    except Exception as exc:
        logger.debug("Baseline lookup failed: %s", exc)
        return None


# ── Network status check ──

def _check_network_pending(capture_data: StepCaptureData) -> bool:
    """Check if any network requests are still pending (no response captured)."""
    for req in capture_data.network_requests:
        if "response" not in req:
            return True
    return False


# ── Main diagnosis generator ──

async def diagnose_failed_step(
    page: Page,
    db: AsyncSession,
    ctx: StepContext,
    result: StepResult,
    capture_data: StepCaptureData,
) -> StepDiagnosis:
    """Generate a full diagnosis for a failed step and persist it."""

    selector = ctx.params.get("selector") or ctx.params.get("from_selector")
    error_text = result.error or ""
    error_type = _classify_error(error_text)

    # DOM probe
    probe = await _probe_selector(page, selector)

    # Viewport
    viewport = await _get_viewport_info(page)

    # Candidate selectors
    candidates = await _find_candidate_selectors(page, selector)

    # Baseline
    baseline = await _find_baseline_screenshot(db, ctx.run_id, ctx.step_index)

    # Network pending
    network_pending = _check_network_pending(capture_data)

    # Suggest scroll if element exists but is outside viewport
    suggest_scroll = False
    if probe.get("exists") and probe.get("bbox"):
        bb = probe["bbox"]
        if bb["y"] + bb["height"] < 0 or bb["y"] > viewport["height"]:
            suggest_scroll = True

    # Suggest retry for stale/detached errors
    suggest_retry = error_type == "StaleElementError"

    # Suggest wait if network is pending or timeout on invisible element
    suggest_wait = network_pending or (
        error_type == "TimeoutError" and probe.get("exists") and not probe.get("visible")
    )

    # Build payload
    payload = {
        "summary": {
            "action": ctx.action,
            "error_text": error_text,
            "error_type": error_type,
            "selector": selector,
            "step_index": ctx.step_index,
        },
        "context": {
            "screenshot_url": f"/screenshots/{ctx.run_id}/{ctx.step_index}_after.png",
            "dom_exists": probe.get("exists", False),
            "dom_visible": probe.get("visible", False),
            "dom_obscured": probe.get("obscured", False),
            "viewport_info": viewport,
            "page_url": page.url,
            "page_title": await page.title(),
            "expected_url": ctx.params.get("url") if ctx.action == "goto" else None,
        },
        "visual_diff": {
            "has_baseline": baseline is not None,
            "baseline_run_id": baseline["run_id"] if baseline else None,
            "baseline_screenshot_url": baseline["screenshot_url"] if baseline else None,
            "baseline_run_started_at": baseline["run_started_at"] if baseline else None,
            "current_screenshot_url": f"/screenshots/{ctx.run_id}/{ctx.step_index}_after.png",
            "diff_note": _generate_diff_note(probe, error_type),
        },
        "fixes": {
            "candidate_selectors": candidates,
            "suggest_wait": suggest_wait,
            "suggest_scroll": suggest_scroll,
            "suggest_retry": suggest_retry,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Persist to DB
    diagnosis = StepDiagnosis(
        run_id=ctx.run_id,
        step_index=ctx.step_index,
        payload_json=payload,
    )
    db.add(diagnosis)
    await db.flush()

    return diagnosis


def _generate_diff_note(probe: dict, error_type: str) -> str:
    if error_type == "TimeoutError":
        if not probe.get("exists"):
            return "目标元素在 DOM 中未找到，可能是 selector 失效或页面未加载完成"
        if not probe.get("visible"):
            return "元素存在于 DOM 中但不可见，可能被隐藏或需要等待动画"
        if probe.get("obscured"):
            return "元素被其他元素遮挡，可能有关闭弹窗或遮罩层"
        return "操作超时，原因待进一步分析"
    if error_type == "SelectorError":
        return "Selector 无效或格式错误"
    if error_type == "NavigationError":
        return "页面导航失败，可能 URL 错误或网络问题"
    if error_type == "StaleElementError":
        return "DOM 元素在操作过程中被移除或替换，建议重试"
    return "未知错误，建议查看截图和 DOM 快照"
