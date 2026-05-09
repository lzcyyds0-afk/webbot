"""AI Scout: URL → test path suggestions.

Workflow:
1. Open URL with Playwright (with optional cookies), wait for networkidle + 500ms
2. Take screenshot + extract interactive element summary
3. Send screenshot + summary + optional goal to vision LLM with scout prompt
4. Parse response as JSON array of ScoutPath objects
5. Validate structure; on failure, retry once
6. Return ScoutResponse with paths + snapshot metadata
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from playwright.async_api import Page
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.browser import BrowserManager
from app.engine.snapshot import take_snapshot, PageSnapshot
from app.llm import get_provider, Message, ImageRef
from app.models.llm_config import LLMConfig

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "scout.md"

# ── Valid DSL actions ──
_VALID_ACTIONS = {"goto", "click", "input", "wait", "screenshot", "drag", "connect"}


# ── Schemas ──

class ScoutPath(BaseModel):
    title: str
    description: str
    steps: list[dict]
    risk_level: int = Field(..., ge=1, le=5)
    tags: list[str] = []


class ScoutRequest(BaseModel):
    url: str
    goal: str | None = None
    cookies: list[dict] | None = None


class ScoutResponse(BaseModel):
    url: str
    page_title: str
    screenshot_b64: str | None = None
    elements_count: int = 0
    paths: list[ScoutPath]
    raw_llm_output: str | None = None
    retry_used: bool = False


class ScoutError(Exception):
    pass


# ── Public API ──

async def scout_page(req: ScoutRequest, db: AsyncSession) -> ScoutResponse:
    """Main entry: URL → test path suggestions."""

    # 1. Load default LLM config
    config = await _load_default_llm_config(db)
    provider = get_provider(config)

    # 2. Open page, take snapshot
    snapshot = await _take_page_snapshot(req.url, cookies=req.cookies)

    # 3. Build prompt messages
    system_prompt = _load_system_prompt()
    user_content = _build_user_prompt(snapshot, req.url, req.goal)
    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=user_content),
    ]
    images = [ImageRef(
        type="base64",
        data=snapshot.screenshot_b64,
        media_type="image/png",
    )]

    # 4. Call vision LLM (with one retry on validation failure)
    paths, raw_output, retry_used = await _call_and_validate(
        provider, messages, images
    )

    return ScoutResponse(
        url=snapshot.url,
        page_title=snapshot.title,
        screenshot_b64=snapshot.screenshot_b64,
        elements_count=len(snapshot.elements),
        paths=paths,
        raw_llm_output=raw_output,
        retry_used=retry_used,
    )


# ── Internals ──

async def _load_default_llm_config(db: AsyncSession) -> LLMConfig:
    result = await db.execute(select(LLMConfig).where(LLMConfig.is_default == True))
    config = result.scalar_one_or_none()
    if config is None:
        result = await db.execute(select(LLMConfig).order_by(LLMConfig.id))
        config = result.scalars().first()
    if config is None:
        raise ScoutError("No LLM config available")
    return config


async def _take_page_snapshot(
    url: str,
    cookies: list[dict] | None = None,
) -> PageSnapshot:
    """Open URL in Playwright, optionally set cookies, navigate, take snapshot."""
    bm = BrowserManager(headless=True)
    try:
        await bm.start()
        context = await bm.browser.new_context(
            viewport={"width": 1440, "height": 900},
        )

        # Set cookies if provided (reuse validation from generate.py)
        if cookies:
            pw_cookies = _convert_cookies(cookies)
            if pw_cookies:
                await context.add_cookies(pw_cookies)

        page = await context.new_page()

        # Navigate with networkidle + extra wait
        await page.goto(url, wait_until="networkidle", timeout=20_000)
        await page.wait_for_timeout(500)

        snapshot = await take_snapshot(page, max_elements=60)
        return snapshot

    finally:
        try:
            await bm.close()
        except Exception:
            pass


def _convert_cookies(cookies: list[dict]) -> list[dict]:
    """Validate and convert raw cookie dicts to Playwright format."""
    pw_cookies: list[dict] = []
    for i, c in enumerate(cookies):
        if not isinstance(c, dict):
            logger.warning("Cookie #%d is not a dict, skipping", i)
            continue
        for required in ("name", "value", "domain"):
            if required not in c or c[required] in (None, ""):
                logger.warning("Cookie #%d missing '%s', skipping", i, required)
                break
        else:
            domain = c["domain"]
            if domain.startswith("."):
                domain = domain[1:]
            pw_c: dict = {
                "name": str(c["name"]),
                "value": str(c["value"]),
                "domain": domain,
                "path": str(c.get("path", "/")),
            }
            expires = c.get("expires")
            if expires is not None:
                try:
                    pw_c["expires"] = int(expires)
                except (ValueError, TypeError):
                    pass
            for bool_field in ("httpOnly", "secure"):
                val = c.get(bool_field)
                if val is not None:
                    pw_c[bool_field] = bool(val)
            same_site = c.get("sameSite")
            if same_site is not None:
                same_site = str(same_site)
                if same_site in ("Strict", "Lax", "None"):
                    pw_c["sameSite"] = same_site
            pw_cookies.append(pw_c)
    return pw_cookies


def _load_system_prompt() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("Prompt template not found at %s, using fallback", _PROMPT_PATH)
        return _FALLBACK_SYSTEM


_FALLBACK_SYSTEM = (
    "你是 Web 测试策略专家。根据网页截图和可交互元素列表，"
    "输出 5-10 条测试路径建议，每条包含 title、description、steps（DSL JSON）、"
    "risk_level（1-5）、tags。"
    "输出 ONLY JSON：{\"paths\": [...]}。不要 markdown 围栏。"
)


def _build_user_prompt(snapshot: PageSnapshot, url: str, goal: str | None) -> str:
    """Build the user message with page context and optional goal."""
    parts = [
        f"## Page URL\n{url}",
        f"## Page Title\n{snapshot.title}",
        f"## Interactive Elements\n{snapshot.elements_text(max_elements=60)}",
    ]
    if goal:
        parts.append(f"## 探索目标\n{goal}")
    else:
        parts.append("## 探索目标\n全面探索页面，找出所有值得测试的用户路径")
    return "\n\n".join(parts)


async def _call_and_validate(
    provider,
    messages: list[Message],
    images: list[ImageRef],
) -> tuple[list[ScoutPath], str, bool]:
    """Call vision LLM and validate output. Retry once on validation failure."""
    retry_used = False
    raw_output = ""

    for attempt in range(2):
        try:
            chat_result = await provider.vision(
                messages=messages,
                images=images,
                temperature=0.3,
                max_tokens=4096,
            )
            raw_output = chat_result.content
            parsed = _parse_scout_json(raw_output)
            paths = _validate_paths(parsed)
            return paths, raw_output, retry_used

        except (ParseError, ValidationError) as exc:
            logger.warning(
                "Scout validation failed (attempt %d): %s",
                attempt + 1, exc,
            )
            if attempt == 0:
                retry_used = True
                messages = list(messages) + [
                    Message(role="assistant", content=raw_output),
                    Message(
                        role="user",
                        content=(
                            f"Your output was invalid: {exc}\n\n"
                            "Please fix and output ONLY a valid JSON object with a 'paths' array. "
                            "Each path must have title, description, steps (array of step objects with 'action'), "
                            "risk_level (integer 1-5), and tags (string array). "
                            "No markdown fences."
                        ),
                    ),
                ]
                images = []
            else:
                raise ScoutError(
                    f"Failed to generate valid scout result after 2 attempts. Last error: {exc}"
                ) from exc

    raise ScoutError("Unexpected error in scout loop")


# ── JSON parsing ──

class ParseError(Exception):
    pass


class ValidationError(Exception):
    pass


def _parse_scout_json(text: str) -> dict:
    """Parse LLM response text into a dict."""
    text = text.strip()
    # Strip markdown code fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    # Try to find JSON object in text
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            data = json.loads(brace_match.group())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    raise ParseError(f"Could not extract JSON object from response: {text[:300]}")


def _validate_paths(parsed: dict) -> list[ScoutPath]:
    """Validate parsed dict and return list of ScoutPath."""
    paths_data = parsed.get("paths")
    if not isinstance(paths_data, list):
        raise ValidationError("'paths' must be an array")
    if not paths_data:
        raise ValidationError("'paths' array is empty")
    if len(paths_data) > 20:
        raise ValidationError(f"Too many paths: {len(paths_data)} (max 20)")

    result: list[ScoutPath] = []
    for i, p in enumerate(paths_data):
        if not isinstance(p, dict):
            raise ValidationError(f"Path {i} is not an object")
        for field in ("title", "description", "steps", "risk_level"):
            if field not in p:
                raise ValidationError(f"Path {i} missing required field '{field}'")
        steps = p["steps"]
        if not isinstance(steps, list):
            raise ValidationError(f"Path {i} 'steps' must be an array")
        for j, step in enumerate(steps):
            if not isinstance(step, dict):
                raise ValidationError(f"Path {i} step {j} is not an object")
            action = step.get("action")
            if action not in _VALID_ACTIONS:
                raise ValidationError(
                    f"Path {i} step {j}: invalid action '{action}'. Valid: {sorted(_VALID_ACTIONS)}"
                )
        # Validate risk_level is int 1-5
        rl = p["risk_level"]
        if not isinstance(rl, int) or not (1 <= rl <= 5):
            raise ValidationError(f"Path {i} 'risk_level' must be integer 1-5, got {rl}")
        # tags should be list of strings
        tags = p.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        tags = [str(t) for t in tags]

        result.append(ScoutPath(
            title=str(p["title"]),
            description=str(p["description"]),
            steps=steps,
            risk_level=rl,
            tags=tags,
        ))
    return result
