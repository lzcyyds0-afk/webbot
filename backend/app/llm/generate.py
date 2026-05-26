"""NL → DSL step generator (Enhanced).

Workflow:
1. Use Playwright to open the URL (with optional cookies), take screenshot + element summary
2. Load few-shot examples from prompts/examples/ and optional reference case steps
3. Build enhanced prompt with goal + elements + examples + reference style
4. Send screenshot + prompt to vision LLM
5. Parse response as JSON array of step objects
6. Validate against DSL schema; on failure, auto-repair by sending error back to LLM
7. Return validated steps

New capabilities:
- reference_case_id: use existing test case as style reference (few-shot)
- Few-shot example library in prompts/examples/
- Enhanced auto-repair with structured error feedback
- Refine endpoint for multi-round modification
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.browser import BrowserManager
from app.engine.snapshot import take_snapshot, PageSnapshot
from app.llm import get_provider, Message, ImageRef
from app.models.llm_config import LLMConfig
from app.models.test_case import TestCase

logger = logging.getLogger(__name__)

# ── Prompt template ──
_PROMPT_PATH = Path(__file__).parent / "prompts" / "intent_to_steps.md"
_EXAMPLES_DIR = Path(__file__).parent / "prompts" / "examples"

# ── Valid DSL actions and their required fields ──
_ACTION_SCHEMA: dict[str, set[str]] = {
    "goto": {"url"},
    "click": {"selector"},
    "input": {"selector", "text"},
    "wait": set(),       # ms or selector, at least one
    "screenshot": set(),  # no required fields
    # drag: from_selector OR from_point; to_selector OR to_point.
    # Optional: offset {dx,dy}, steps, hold_ms, mode ("mouse"|"html5"), scroll.
    "drag": set(),
    "connect": {"from_port_selector"},  # to_port_selector OR to_point
    # login: requires username + password; optional url, selectors, success_url_pattern, success_selector.
    "login": {"username", "password"},
}


# ── Schemas ──

class GenerateRequest(BaseModel):
    project_id: int
    url: str
    goal: str
    llm_config_id: int
    cookies: list[dict] | None = None
    """Each cookie: {name, value, domain, path?, expires?, httpOnly?, secure?, sameSite?}"""
    thorough: bool = False
    """If True, generate comprehensive steps covering all interactive elements."""
    reference_case_id: int | None = None
    """If provided, use this test case's steps as style reference."""


class GenerateResponse(BaseModel):
    steps: list[dict]
    screenshot_b64: str | None = None
    elements_text: str | None = None
    raw_llm_output: str | None = None
    retry_used: bool = False


class RefineRequest(BaseModel):
    steps: list[dict]
    user_feedback: str
    llm_config_id: int


class RefineResponse(BaseModel):
    steps: list[dict]
    raw_llm_output: str | None = None


class GenerateError(Exception):
    pass


# ──────────────────────────────────────────────
#  Public API: Generate
# ──────────────────────────────────────────────

async def generate_steps(
    req: GenerateRequest,
    db: AsyncSession,
) -> GenerateResponse:
    """Main entry: NL goal → DSL steps."""

    # 1. Load LLM config
    config = await _load_llm_config(db, req.llm_config_id)
    provider = get_provider(config)

    # 2. Open page, take snapshot
    snapshot = await _take_page_snapshot(req.url, cookies=req.cookies)

    # 3. Load reference case steps if provided
    reference_steps = None
    if req.reference_case_id is not None:
        reference_steps = await _load_reference_steps(db, req.reference_case_id)

    # 4. Build prompt messages
    system_prompt = _load_system_prompt()
    user_content = _build_user_prompt(
        snapshot=snapshot,
        url=req.url,
        goal=req.goal,
        thorough=req.thorough,
        reference_steps=reference_steps,
    )
    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=user_content),
    ]
    images = [ImageRef(
        type="base64",
        data=snapshot.screenshot_b64,
        media_type="image/png",
    )]

    # 5. Call vision LLM (with one retry on validation failure)
    steps, raw_output, retry_used = await _call_and_validate(
        provider, messages, images
    )

    return GenerateResponse(
        steps=steps,
        screenshot_b64=snapshot.screenshot_b64,
        elements_text=snapshot.elements_text(),
        raw_llm_output=raw_output,
        retry_used=retry_used,
    )


# ──────────────────────────────────────────────
#  Public API: Refine
# ──────────────────────────────────────────────

async def refine_steps(
    req: RefineRequest,
    db: AsyncSession,
) -> RefineResponse:
    """Modify existing steps based on user feedback."""

    config = await _load_llm_config(db, req.llm_config_id)
    provider = get_provider(config)

    system_prompt = (
        "You are a web automation engineer. The user has an existing test step sequence "
        "and wants to modify it based on their feedback. "
        "Output ONLY a JSON array of the modified step objects. "
        "Preserve the structure and style of the original steps as much as possible. "
        "Valid actions: goto, click, input, wait, screenshot, drag, connect."
    )

    user_content = (
        "## Current Steps\n"
        f"```json\n{json.dumps(req.steps, ensure_ascii=False, indent=2)}\n```\n\n"
        "## User Feedback\n"
        f"{req.user_feedback}\n\n"
        "Please output the modified steps as a JSON array. No markdown fences."
    )

    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=user_content),
    ]

    chat_result = await provider.chat(
        messages=messages,
        temperature=0.2,
        max_tokens=4096,
    )
    raw_output = chat_result.content
    steps = _parse_steps_json(raw_output)
    _validate_steps(steps)

    return RefineResponse(steps=steps, raw_llm_output=raw_output)


# ──────────────────────────────────────────────
#  Internals
# ──────────────────────────────────────────────

async def _load_llm_config(db: AsyncSession, config_id: int) -> LLMConfig:
    result = await db.execute(
        select(LLMConfig).where(LLMConfig.id == config_id)
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise GenerateError(f"LLMConfig {config_id} not found")
    return config


async def _load_reference_steps(db: AsyncSession, case_id: int) -> list[dict] | None:
    """Load steps from a reference test case to use as style example."""
    result = await db.execute(
        select(TestCase).where(TestCase.id == case_id)
    )
    tc = result.scalar_one_or_none()
    if tc is None:
        logger.warning("Reference test case %d not found", case_id)
        return None
    steps = tc.steps_json if isinstance(tc.steps_json, list) else []
    if not steps:
        logger.warning("Reference test case %d has no steps", case_id)
        return None
    return steps


def _load_few_shot_examples() -> str:
    """Load all .md example files from prompts/examples/."""
    if not _EXAMPLES_DIR.exists():
        return ""
    parts: list[str] = []
    for path in sorted(_EXAMPLES_DIR.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
            parts.append(text)
        except Exception as exc:
            logger.warning("Failed to read example %s: %s", path, exc)
    return "\n\n".join(parts)


async def _take_page_snapshot(
    url: str,
    cookies: list[dict] | None = None,
) -> PageSnapshot:
    """Open URL in Playwright, optionally set cookies, take snapshot."""
    bm = BrowserManager(headless=True)
    try:
        await bm.start()
        context = await bm.browser.new_context(
            viewport={"width": 1440, "height": 900},
        )

        # Set cookies if provided
        if cookies:
            pw_cookies = []
            for i, c in enumerate(cookies):
                if not isinstance(c, dict):
                    raise GenerateError(f"Cookie #{i} must be an object, got {type(c).__name__}")
                for required_field in ("name", "value", "domain"):
                    if required_field not in c or c[required_field] in (None, ""):
                        raise GenerateError(f"Cookie #{i} missing required field '{required_field}'")

                domain = c["domain"]
                # Strip leading dot for CDP compatibility (e.g. ".example.com" -> "example.com")
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
                        raise GenerateError(
                            f"Cookie #{i} ('{c['name']}'): 'expires' must be an integer (Unix timestamp)"
                        )

                for bool_field in ("httpOnly", "secure"):
                    val = c.get(bool_field)
                    if val is not None:
                        pw_c[bool_field] = bool(val)

                same_site = c.get("sameSite")
                if same_site is not None:
                    same_site = str(same_site)
                    if same_site not in ("Strict", "Lax", "None"):
                        raise GenerateError(
                            f"Cookie #{i} ('{c['name']}'): 'sameSite' must be 'Strict', 'Lax' or 'None'"
                        )
                    pw_c["sameSite"] = same_site
                    # sameSite=None requires secure=True in modern browsers
                    if same_site == "None" and not pw_c.get("secure"):
                        pw_c["secure"] = True
                        logger.info("Cookie '%s': auto-enabled secure=True because sameSite=None", c["name"])

                pw_cookies.append(pw_c)

            try:
                await context.add_cookies(pw_cookies)
                logger.info("Added %d cookies for domain(s): %s", len(pw_cookies), ", ".join({c["domain"] for c in pw_cookies}))
            except Exception as exc:
                logger.error("Failed to add cookies: %s", pw_cookies)
                raise GenerateError(
                    f"Invalid cookies for target URL '{url}'. "
                    f"Ensure cookie 'domain' matches the page domain (e.g. 'mon.zijieapi.com'). "
                    f"Original error: {exc}"
                ) from exc

        page = await context.new_page()

        # Navigate
        await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
        # Wait a bit for dynamic content / auth checks to settle
        await page.wait_for_timeout(1500)

        # If cookies were provided but page may still be on login, try a reload
        # Some SPAs only pick up session cookies after the first navigation cycle
        if cookies:
            try:
                logger.info("Reloading page to ensure cookies take effect...")
                await page.reload(wait_until="domcontentloaded", timeout=20_000)
                await page.wait_for_timeout(1500)
            except Exception as exc:
                logger.warning("Page reload failed, continuing with current page state: %s", exc)

        snapshot = await take_snapshot(page)
        return snapshot

    finally:
        try:
            await bm.close()
        except Exception:
            pass


def _load_system_prompt() -> str:
    try:
        template = _PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("Prompt template not found at %s, using fallback", _PROMPT_PATH)
        return _FALLBACK_SYSTEM

    # Inject few-shot examples
    examples = _load_few_shot_examples()
    return template.replace("{examples}", examples)


_FALLBACK_SYSTEM = (
    "You are a web automation expert. Given a screenshot, element summary, and goal, "
    "output a JSON array of test steps. Each step has an 'action' field and parameters. "
    "Valid actions: goto, click, input, wait, screenshot, drag, connect. "
    "Output ONLY the JSON array, no markdown fences."
)


def _build_user_prompt(
    snapshot: PageSnapshot,
    url: str,
    goal: str,
    *,
    thorough: bool = False,
    reference_steps: list[dict] | None = None,
) -> str:
    """Build the user message with page context, goal, and optional reference."""
    parts = [
        f"## Page URL\n{url}",
        f"## Page Title\n{snapshot.title}",
        f"## Interactive Elements\n{snapshot.elements_text()}",
        f"## Goal\n{goal}",
    ]

    if reference_steps:
        parts.append(
            "## Reference Steps (style guide)\n"
            "Follow the style, selector patterns, and wait spacing of these reference steps:\n"
            f"```json\n{json.dumps(reference_steps, ensure_ascii=False, indent=2)}\n```"
        )

    if thorough:
        parts.append(
            "## Mode: THOROUGH EXPLORATION\n"
            "Generate as many steps as needed to thoroughly cover ALL interactive elements on the page. "
            "Click every button, fill every input field, and interact with every clickable element. "
            "Do NOT stop at the minimal path — explore the page comprehensively."
        )

    # The template has {reference_steps} placeholder; we replace it here
    # Actually the system prompt handles {examples}, and reference steps go in user content
    return "\n\n".join(parts)


async def _call_and_validate(
    provider,
    messages: list[Message],
    images: list[ImageRef],
) -> tuple[list[dict], str, bool]:
    """Call vision LLM and validate output. Retry once on validation failure.

    Returns (steps, raw_output, retry_used).
    """
    retry_used = False
    raw_output = ""

    for attempt in range(2):
        try:
            chat_result = await provider.vision(
                messages=messages,
                images=images,
                temperature=0.2,
                max_tokens=4096,
            )
            raw_output = chat_result.content
            steps = _parse_steps_json(raw_output)
            _validate_steps(steps)
            return steps, raw_output, retry_used

        except (_ParseError, ValidationError) as exc:
            logger.warning(
                "Generate steps validation failed (attempt %d): %s",
                attempt + 1, exc,
            )
            if attempt == 0:
                # Enhanced auto-repair: send error + current steps + schema back to LLM
                retry_used = True
                # Try to extract partial steps to help LLM understand what was generated
                partial_steps = ""
                try:
                    partial = _parse_steps_json(raw_output)
                    partial_steps = json.dumps(partial, ensure_ascii=False, indent=2)
                except Exception:
                    partial_steps = raw_output[:800]

                repair_prompt = _build_repair_prompt(exc, partial_steps)
                messages = list(messages) + [
                    Message(role="assistant", content=raw_output),
                    Message(role="user", content=repair_prompt),
                ]
                # Don't resend images on retry (already in context)
                images = []
            else:
                raise GenerateError(
                    f"Failed to generate valid steps after 2 attempts. Last error: {exc}"
                ) from exc

    raise GenerateError("Unexpected error in generate loop")


def _build_repair_prompt(error: Exception, partial_steps: str) -> str:
    """Build a detailed repair prompt for auto-repair."""
    schema_info = (
        "Required fields per action:\n"
        "- goto: url\n"
        "- click: selector\n"
        "- input: selector, text\n"
        "- wait: ms (number) OR selector (string)\n"
        "- screenshot: no required fields\n"
        "- drag: from_selector, to_selector\n"
        "- connect: from_selector, to_selector\n"
    )
    return (
        f"Your previous output was invalid:\n{error}\n\n"
        f"Schema requirements:\n{schema_info}\n\n"
        "Your previous attempt:\n"
        f"```json\n{partial_steps}\n```\n\n"
        "Please fix ALL issues and output ONLY a valid JSON array of step objects. "
        "Ensure every step has the correct required fields. "
        "No markdown fences, no trailing commas, no comments."
    )


# ── JSON parsing ──

class _ParseError(Exception):
    pass


class ValidationError(Exception):
    pass


def _parse_steps_json(text: str) -> list[dict]:
    """Parse LLM response text into a list of step dicts."""
    text = text.strip()

    # Strip markdown code fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    # Try direct parse
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "steps" in data:
            return data["steps"]
    except json.JSONDecodeError:
        pass

    # Try to find JSON array in text
    bracket_match = re.search(r"\[.*\]", text, re.DOTALL)
    if bracket_match:
        try:
            data = json.loads(bracket_match.group())
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    raise _ParseError(f"Could not extract JSON array from response: {text[:300]}")


def _validate_steps(steps: list[dict]) -> None:
    """Validate that each step conforms to the DSL schema."""
    if not steps:
        raise ValidationError("Steps array is empty")

    valid_actions = set(_ACTION_SCHEMA.keys())

    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValidationError(f"Step {i} is not an object: {step}")

        action = step.get("action")
        if action not in valid_actions:
            raise ValidationError(
                f"Step {i}: invalid action '{action}'. Valid: {sorted(valid_actions)}"
            )

        required = _ACTION_SCHEMA[action]
        for field in required:
            if field not in step:
                raise ValidationError(
                    f"Step {i} ({action}): missing required field '{field}'"
                )

        # Special: wait needs at least ms or selector
        if action == "wait" and "ms" not in step and "selector" not in step:
            raise ValidationError(
                f"Step {i} (wait): needs at least 'ms' or 'selector'"
            )

        # Special: drag needs source AND target
        if action == "drag":
            has_src = ("from_selector" in step) or ("from_point" in step)
            has_dst = ("to_selector" in step) or ("to_point" in step)
            if not has_src:
                raise ValidationError(
                    f"Step {i} (drag): needs 'from_selector' or 'from_point'"
                )
            if not has_dst:
                raise ValidationError(
                    f"Step {i} (drag): needs 'to_selector' or 'to_point'"
                )

        # Special: connect needs source port AND (target port or point)
        if action == "connect":
            has_dst = ("to_port_selector" in step) or ("to_point" in step)
            if not has_dst:
                raise ValidationError(
                    f"Step {i} (connect): needs 'to_port_selector' or 'to_point'"
                )
