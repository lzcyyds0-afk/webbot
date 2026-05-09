"""Page snapshot utility: take screenshot + extract interactive element summary.

Used by the NL→DSL generator to capture the current page state before
sending it to the vision LLM.
"""
from __future__ import annotations

import base64
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from playwright.async_api import Page

logger = logging.getLogger(__name__)

# Roles that indicate interactivity
_INTERACTIVE_ROLES = frozenset({
    "button", "link", "textbox", "searchbox", "combobox",
    "listbox", "menuitem", "tab", "checkbox", "radio",
    "switch", "slider", "spinbutton", "dialog",
    "treeitem", "gridcell", "menuitemcheckbox", "menuitemradio",
})

# ARIA roles that suggest draggability
_DRAGGABLE_ROLES = frozenset({
    "treeitem", "listitem", "gridcell", "option",
})


@dataclass
class ElementSummary:
    """Compact representation of one interactive element."""
    role: str
    name: str          # accessible name / text
    selector: str      # CSS or test-id selector
    bbox: dict | None  # {x, y, width, height} or None
    draggable: bool = False
    input_type: str | None = None  # for textbox: "text" / "email" / "password" etc.


@dataclass
class PageSnapshot:
    """Complete snapshot of a page for LLM consumption."""
    screenshot_b64: str              # base64-encoded PNG
    url: str
    title: str
    elements: list[ElementSummary] = field(default_factory=list)

    def elements_text(self, max_elements: int = 60) -> str:
        """Render elements as a compact text block for the LLM prompt.

        Limits output to `max_elements` to avoid token explosion.
        """
        lines: list[str] = []
        shown = 0
        for el in self.elements[:max_elements]:
            parts = [f"[{el.role}]"]
            if el.name:
                # Truncate long names
                name = el.name[:80] + ("..." if len(el.name) > 80 else "")
                parts.append(f'"{name}"')
            parts.append(f"selector={el.selector}")
            if el.bbox:
                parts.append(
                    f"pos=({el.bbox['x']},{el.bbox['y']}) "
                    f"size={el.bbox['width']}x{el.bbox['height']}"
                )
            if el.draggable:
                parts.append("draggable")
            if el.input_type:
                parts.append(f"type={el.input_type}")
            lines.append(" ".join(parts))
            shown += 1

        if len(self.elements) > max_elements:
            lines.append(f"... and {len(self.elements) - max_elements} more elements")

        return "\n".join(lines)


async def take_snapshot(
    page: Page,
    *,
    full_page: bool = False,
    max_elements: int = 60,
) -> PageSnapshot:
    """Take a screenshot and extract interactive element summaries.

    Steps:
    1. Screenshot the page (viewport or full_page)
    2. Run JS to query all elements with ARIA roles
    3. Filter to interactive roles only
    4. Build ElementSummary list
    """
    # 1. Screenshot
    screenshot_bytes = await page.screenshot(full_page=full_page)
    screenshot_b64 = base64.b64encode(screenshot_bytes).decode()

    # Page may have navigated; re-read url/title safely
    try:
        url = page.url
    except Exception:
        url = ""
    try:
        title = await page.title()
    except Exception:
        title = ""

    # 2. Extract elements via JS
    elements = await _extract_elements(page)

    return PageSnapshot(
        screenshot_b64=screenshot_b64,
        url=url,
        title=title,
        elements=elements[:max_elements],
    )


async def _extract_elements(page: Page) -> list[ElementSummary]:
    """Run JavaScript in the page to extract interactive elements.

    Uses the Accessibility tree where possible, falling back to
    a DOM query for common interactive tags.
    """
    js_code = """
    () => {
        const results = [];
        const seen = new Set();

        // Strategy 1: Use ARIA role-based query
        const interactiveRoles = [
            'button', 'link', 'textbox', 'searchbox', 'combobox',
            'listbox', 'menuitem', 'tab', 'checkbox', 'radio',
            'switch', 'slider', 'spinbutton', 'dialog',
            'treeitem', 'gridcell', 'menuitemcheckbox', 'menuitemradio',
        ];

        for (const role of interactiveRoles) {
            const els = document.querySelectorAll(`[role="${role}"]`);
            for (const el of els) {
                const selector = _getSelector(el);
                if (seen.has(selector)) continue;
                seen.add(selector);
                results.push({
                    role: role,
                    name: _getName(el),
                    selector: selector,
                    bbox: _getBBox(el),
                    draggable: el.draggable || role === 'treeitem' || role === 'listitem',
                    inputType: el.type || null,
                });
            }
        }

        // Strategy 2: Common interactive tags without explicit role
        const tags = {
            'a': 'link',
            'button': 'button',
            'input': 'textbox',
            'select': 'combobox',
            'textarea': 'textbox',
            'summary': 'button',
        };
        for (const [tag, defaultRole] of Object.entries(tags)) {
            const els = document.querySelectorAll(tag);
            for (const el of els) {
                if (el.getAttribute('role')) continue;  // already handled
                // Skip hidden/invisible
                if (el.offsetParent === null && el.style.position !== 'fixed') continue;
                const selector = _getSelector(el);
                if (seen.has(selector)) continue;
                seen.add(selector);
                results.push({
                    role: el.type === 'submit' ? 'button' : defaultRole,
                    name: _getName(el),
                    selector: selector,
                    bbox: _getBBox(el),
                    draggable: false,
                    inputType: el.type || null,
                });
            }
        }

        // Strategy 3: Elements with tabindex
        const focusable = document.querySelectorAll('[tabindex]:not([tabindex="-1"])');
        for (const el of focusable) {
            if (el.getAttribute('role')) continue;
            if (el.tagName === 'INPUT' || el.tagName === 'BUTTON' || el.tagName === 'A') continue;
            const selector = _getSelector(el);
            if (seen.has(selector)) continue;
            seen.add(selector);
            results.push({
                role: 'generic',
                name: _getName(el),
                selector: selector,
                bbox: _getBBox(el),
                draggable: el.draggable,
                inputType: null,
            });
        }

        return results;

        function _getName(el) {
            return (
                el.getAttribute('aria-label') ||
                el.getAttribute('title') ||
                el.getAttribute('placeholder') ||
                el.alt ||
                (el.textContent || '').trim().slice(0, 80) ||
                ''
            );
        }

        function _getSelector(el) {
            // Prefer data-testid
            if (el.getAttribute('data-testid')) {
                return `[data-testid="${el.getAttribute('data-testid')}"]`;
            }
            // Prefer id
            if (el.id) {
                return `#${CSS.escape(el.id)}`;
            }
            // Prefer aria-label
            if (el.getAttribute('aria-label')) {
                return `${el.tagName.toLowerCase()}[aria-label="${el.getAttribute('aria-label')}"]`;
            }
            // Prefer stable data- attributes
            for (const attr of el.attributes) {
                if (attr.name.startsWith('data-') && attr.name !== 'data-testid') {
                    return `${el.tagName.toLowerCase()}[${attr.name}="${attr.value}"]`;
                }
            }
            // Prefer text content (if short and unique-looking)
            const text = (el.textContent || '').trim();
            if (text && text.length <= 40 && !/[\r\n]/.test(text)) {
                return `${el.tagName.toLowerCase()}:has-text("${text.replace(/"/g, '\\"')}")`;
            }
            // Build tag + classes, but filter out utility classes
            const tag = el.tagName.toLowerCase();
            const utilityPrefixes = ['border', 'shadow', 'bg-', 'text-', 'p-', 'm-', 'w-', 'h-', 'flex', 'grid', 'block', 'inline', 'relative', 'absolute', 'hidden', 'visible', 'overflow'];
            const cls = el.className && typeof el.className === 'string'
                ? '.' + el.className.trim().split(/\\s+/)
                    .filter(c => !utilityPrefixes.some(p => c.startsWith(p)))
                    .slice(0, 2)
                    .join('.')
                : '';
            return tag + cls || tag;
        }

        function _getBBox(el) {
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 && rect.height === 0) return null;
            return {
                x: Math.round(rect.x),
                y: Math.round(rect.y),
                width: Math.round(rect.width),
                height: Math.round(rect.height),
            };
        }
    }
    """

    try:
        raw_elements = await page.evaluate(js_code)
    except Exception as exc:
        logger.warning("Element extraction JS failed: %s", exc)
        return []

    results: list[ElementSummary] = []
    for item in raw_elements:
        try:
            results.append(ElementSummary(
                role=item.get("role", "generic"),
                name=item.get("name", ""),
                selector=item.get("selector", ""),
                bbox=item.get("bbox"),
                draggable=item.get("draggable", False),
                input_type=item.get("inputType"),
            ))
        except Exception:
            continue

    return results
