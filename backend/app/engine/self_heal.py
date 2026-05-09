"""Self-healing selector resolution for flaky/broken locators.

Three-layer fallback:
1. Rule layer: strip nth-of-type, match by tag+text, aria-label, data-testid
2. DOM semantic layer: use LLM to find the semantically closest element
3. Vision layer: TODO — use VLM on screenshots

Only triggered when a selector is not found or not visible before action execution.
Success path has zero overhead.
"""
from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.async_api import Page, TimeoutError as PwTimeout
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.engine.models import StepContext
from app.llm import get_provider, Message, ImageRef
from app.models.heal_event import HealEvent
from app.models.llm_config import LLMConfig

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "self_heal.md"


@dataclass
class HealResult:
    healed_selector: str
    method: str          # "rule" | "llm" | "vision"
    llm_cost: float | None = None


class SelfHealEngine:
    """Attempts to fix broken selectors before failing the step."""

    def __init__(self, db: AsyncSession | None = None) -> None:
        self._db = db

    async def try_heal(
        self,
        page: Page,
        original_selector: str,
        ctx: StepContext,
    ) -> HealResult | None:
        """Try rule → LLM → vision fallback. Return None if all fail."""
        if not settings.self_heal_enabled:
            return None

        # Layer a: rule-based
        healed = await self._rule_heal(page, original_selector)
        if healed:
            logger.info("Rule heal success: %s → %s", original_selector, healed)
            return HealResult(healed_selector=healed, method="rule")

        # Layer b: DOM semantic (LLM)
        if self._db is not None:
            healed, cost = await self._llm_heal(page, original_selector, ctx)
            if healed:
                logger.info("LLM heal success: %s → %s", original_selector, healed)
                return HealResult(healed_selector=healed, method="llm", llm_cost=cost)

        # Layer c: vision (TODO)
        # healed = await self._vision_heal(page, original_selector, ctx)
        # if healed:
        #     return HealResult(healed_selector=healed, method="vision")

        logger.info("Self-heal failed for selector: %s", original_selector)
        return None

    # ──────────────────────────────
    #  Layer a: Rule-based
    # ──────────────────────────────

    async def _rule_heal(self, page: Page, selector: str) -> str | None:
        """Try rule-based selector recovery."""
        # Strategy 1: strip :nth-of-type() / :nth-child()
        stripped = re.sub(r":nth-of-type\(\d+\)", "", selector)
        stripped = re.sub(r":nth-child\(\d+\)", "", stripped)
        if stripped != selector:
            if await _selector_works(page, stripped):
                return stripped

        # Strategy 2: extract tag + text content, rebuild with :has-text()
        tag_text = await _try_tag_text_match(page, selector)
        if tag_text and await _selector_works(page, tag_text):
            return tag_text

        # Strategy 3: try aria-label or data-testid from original element
        # (if the selector ever matched before, we might have it in history)
        # This is a no-op for first-time failures.

        # Strategy 4: simplify compound selectors (e.g. button.btn-primary.shadow
        # → button.btn-primary, button.shadow, button)
        simplified = await _try_simplify_selector(page, selector)
        if simplified:
            return simplified

        return None

    # ──────────────────────────────
    #  Layer b: DOM semantic (LLM)
    # ──────────────────────────────

    async def _llm_heal(
        self, page: Page, original_selector: str, ctx: StepContext
    ) -> tuple[str | None, float | None]:
        """Use LLM to find the semantically closest element in current DOM."""
        if self._db is None:
            return None, None

        try:
            config = await _load_default_llm_config(self._db)
            provider = get_provider(config)
        except Exception as exc:
            logger.warning("LLM heal skipped: no default config. %s", exc)
            return None, None

        # Gather DOM context
        dom_summary = await _extract_visible_elements(page)
        original_info = await _describe_selector_in_dom(page, original_selector)

        prompt = _build_heal_prompt(original_selector, original_info, dom_summary)
        messages = [Message(role="user", content=prompt)]

        try:
            chat_result = await provider.chat(
                messages=messages,
                temperature=0.1,
                max_tokens=2048,
            )
            raw = chat_result.content.strip()
            healed = _extract_selector_from_llm_response(raw)
            if healed and await _selector_works(page, healed):
                cost = _estimate_cost(chat_result.usage)
                return healed, cost
        except Exception as exc:
            logger.warning("LLM heal call failed: %s", exc)

        return None, None

    # ──────────────────────────────
    #  Layer c: Vision (TODO)
    # ──────────────────────────────

    async def _vision_heal(
        self, page: Page, original_selector: str, ctx: StepContext
    ) -> str | None:
        """TODO: use VLM to locate the element visually."""
        return None


# ── Helpers ──

async def _selector_works(page: Page, selector: str, timeout_ms: int = 3000) -> bool:
    """Check if selector finds at least one visible element."""
    try:
        count = await page.locator(selector).count()
        if count == 0:
            return False
        return await page.locator(selector).first.is_visible(timeout=timeout_ms)
    except (PwTimeout, Exception):
        return False


async def _try_tag_text_match(page: Page, selector: str) -> str | None:
    """Extract tag and text from the selector's intended element, try :has-text()."""
    try:
        info = await page.evaluate(
            """(selector) => {
                const el = document.querySelector(selector);
                if (!el) return null;
                return {
                    tag: el.tagName.toLowerCase(),
                    text: (el.textContent || '').trim().slice(0, 40),
                    aria_label: el.getAttribute('aria-label') || null,
                    data_testid: el.getAttribute('data-testid') || null,
                };
            }""",
            selector,
        )
        if not info:
            return None

        # Try data-testid first (most stable)
        if info.get("data_testid"):
            candidate = f"{info['tag']}[data-testid=\"{info['data_testid']}\"]"
            if await _selector_works(page, candidate):
                return candidate

        # Try aria-label
        if info.get("aria_label"):
            candidate = f"{info['tag']}[aria-label=\"{info['aria_label']}\"]"
            if await _selector_works(page, candidate):
                return candidate

        # Try text match
        if info.get("text"):
            text = info["text"].replace('"', '\\"')
            candidate = f"{info['tag']}:has-text(\"{text}\")"
            if await _selector_works(page, candidate):
                return candidate
    except Exception:
        pass
    return None


async def _try_simplify_selector(page: Page, selector: str) -> str | None:
    """Try progressively simplifying a compound selector."""
    parts = selector.split()
    for i in range(len(parts) - 1, 0, -1):
        simplified = " ".join(parts[:i])
        if await _selector_works(page, simplified):
            return simplified

    # Try just the tag if there's a class
    tag_match = re.match(r"^([a-zA-Z0-9_-]+)", selector)
    if tag_match:
        tag_only = tag_match.group(1)
        if tag_only != selector and await _selector_works(page, tag_only):
            # Make sure it's not too broad (count <= 5)
            try:
                count = await page.locator(tag_only).count()
                if 0 < count <= 5:
                    return tag_only
            except Exception:
                pass
    return None


async def _extract_visible_elements(page: Page, max_items: int = 30) -> list[dict]:
    """Extract a concise list of visible interactive elements from the page."""
    try:
        return await page.evaluate(
            """(maxItems) => {
                const results = [];
                const els = document.querySelectorAll('button, a, input, select, textarea, [role="button"], [role="link"]');
                for (const el of els) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) continue;
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden') continue;
                    const text = (el.textContent || el.value || el.placeholder || '').trim().slice(0, 40);
                    let sel = '';
                    if (el.id) sel = '#' + CSS.escape(el.id);
                    else if (el.getAttribute('data-testid')) sel = `[data-testid="${el.getAttribute('data-testid')}"]`;
                    else if (el.getAttribute('aria-label')) sel = `${el.tagName.toLowerCase()}[aria-label="${el.getAttribute('aria-label')}"]`;
                    else if (text && text.length <= 30) sel = `${el.tagName.toLowerCase()}:has-text("${text.replace(/"/g, '\\"')}")`;
                    else sel = el.tagName.toLowerCase() + (el.className ? '.' + el.className.trim().split(/\\s+/).slice(0,2).join('.') : '');
                    results.push({
                        tag: el.tagName.toLowerCase(),
                        text: text,
                        selector: sel,
                        aria_label: el.getAttribute('aria-label') || null,
                        data_testid: el.getAttribute('data-testid') || null,
                    });
                    if (results.length >= maxItems) break;
                }
                return results;
            }""",
            max_items,
        )
    except Exception as exc:
        logger.debug("extract_visible_elements failed: %s", exc)
        return []


async def _describe_selector_in_dom(page: Page, selector: str) -> dict | None:
    """Describe what the original selector was supposed to target."""
    try:
        return await page.evaluate(
            """(selector) => {
                const el = document.querySelector(selector);
                if (!el) return null;
                const parent = el.parentElement;
                return {
                    tag: el.tagName.toLowerCase(),
                    text: (el.textContent || '').trim().slice(0, 60),
                    aria_label: el.getAttribute('aria-label') || null,
                    data_testid: el.getAttribute('data-testid') || null,
                    className: el.className || null,
                    parent_tag: parent ? parent.tagName.toLowerCase() : null,
                    parent_text: parent ? (parent.textContent || '').trim().slice(0, 40) : null,
                };
            }""",
            selector,
        )
    except Exception:
        return None


def _build_heal_prompt(original_selector: str, original_info: dict | None, dom_summary: list[dict]) -> str:
    """Build prompt for LLM-based selector healing."""
    parts = [
        "You are a web automation debugging expert. The original CSS selector no longer works.",
        "Given the original selector's intent and the current page's visible elements, find the best matching selector.",
        "",
        "## Original Selector (broken)",
        f"`{original_selector}`",
    ]

    if original_info:
        parts.append("\n## Original Element Description")
        parts.append(f"- tag: {original_info.get('tag')}")
        parts.append(f"- text: {original_info.get('text')}")
        parts.append(f"- aria-label: {original_info.get('aria_label')}")
        parts.append(f"- data-testid: {original_info.get('data_testid')}")
        parts.append(f"- class: {original_info.get('className')}")
        if original_info.get("parent_tag"):
            parts.append(f"- parent: {original_info['parent_tag']} \"{original_info.get('parent_text', '')}\"")

    parts.append("\n## Current Visible Elements")
    for i, el in enumerate(dom_summary[:20], 1):
        line = f"{i}. [{el['tag']}] text=\"{el.get('text', '')}\" selector=`{el['selector']}`"
        if el.get("aria_label"):
            line += f" aria-label=\"{el['aria_label']}\""
        if el.get("data_testid"):
            line += f" data-testid=\"{el['data_testid']}\""
        parts.append(line)

    parts.append("\n## Your Task")
    parts.append("Respond with ONLY a JSON object:")
    parts.append('```json')
    parts.append('{"selector": "the-best-css-selector", "confidence": 0.85, "reason": "why this matches"}')
    parts.append('```')
    parts.append("If no good match exists, return: {\"selector\": null, \"confidence\": 0.0}")

    return "\n".join(parts)


def _extract_selector_from_llm_response(text: str) -> str | None:
    """Extract selector from LLM JSON response."""
    text = text.strip()
    # Strip markdown fences
    fence = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    # Find JSON object
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group())
        selector = data.get("selector")
        if selector and isinstance(selector, str):
            return selector
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _estimate_cost(usage) -> float | None:
    """Rough cost estimate in USD."""
    if not usage:
        return None
    # Approximate: $0.0015 per 1K input + $0.002 per 1K output (GPT-4o-mini rates)
    total = usage.prompt_tokens + usage.completion_tokens
    if total > 0:
        return round(total * 0.000002, 6)
    return None


async def _load_default_llm_config(db: AsyncSession) -> LLMConfig:
    result = await db.execute(select(LLMConfig).where(LLMConfig.is_default == True))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        raise ValueError("No default LLM config found")
    return cfg


# ── Public helpers for Runner ──

async def record_heal_event(
    db: AsyncSession,
    run_id: int,
    step_index: int,
    original_selector: str,
    healed_selector: str,
    method: str = "rule",
    llm_cost: float | None = None,
) -> HealEvent:
    """Persist a heal event to the database."""
    event = HealEvent(
        run_id=run_id,
        step_index=step_index,
        original_selector=original_selector,
        healed_selector=healed_selector,
        method=method,
        llm_cost=llm_cost,
    )
    db.add(event)
    await db.flush()
    return event
