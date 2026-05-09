from __future__ import annotations

import base64
import json
import logging
import re
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import get_provider, Message, ImageRef
from app.models.llm_config import LLMConfig

logger = logging.getLogger(__name__)

# ── Prompt template path ──
_PROMPT_PATH = Path(__file__).parent / "prompts" / "visual_assert.md"

# ── Output directory for annotated images ──
_STORAGE_DIR = Path("storage/visual")


class BBox(BaseModel):
    label: str
    x: int
    y: int
    w: int
    h: int


class VisualResult(BaseModel):
    passed: bool
    confidence: float
    reason: str
    bboxes: list[BBox] = []
    annotated_path: str | None = None


# ──────────────────────────────────────────────
#  Public API
# ──────────────────────────────────────────────

async def analyze(
    screenshot_path: str,
    expectation: str,
    llm_config_id: int,
    *,
    db: AsyncSession,
    run_id: int | None = None,
    step_index: int | None = None,
) -> VisualResult:
    """Analyze a screenshot against a natural-language expectation.

    1. Load screenshot as base64
    2. Load LLMConfig from DB, instantiate provider
    3. Call provider.vision() with the system prompt
    4. Parse JSON response (retry once on parse failure)
    5. Draw annotated image with bboxes
    6. Return VisualResult
    """
    # 1. Load screenshot
    img_b64 = _load_image_base64(screenshot_path)

    # 2. Load LLM config
    config = await _load_config(db, llm_config_id)
    provider = get_provider(config)

    # 3. Build messages
    system_prompt = _load_system_prompt()
    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=f"Expectation: {expectation}"),
    ]
    images = [ImageRef(type="base64", data=img_b64, media_type="image/png")]

    # 4. Call vision (with retry on parse failure)
    result = await _call_and_parse(provider, messages, images)

    # 5. Draw annotated image
    annotated_path = await _draw_annotated(
        screenshot_path,
        result.bboxes,
        run_id=run_id,
        step_index=step_index,
    )
    result.annotated_path = str(annotated_path) if annotated_path else None

    return result


# ──────────────────────────────────────────────
#  Internals
# ──────────────────────────────────────────────

def _load_image_base64(path: str) -> str:
    """Read an image file and return base64-encoded string."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


async def _load_config(db: AsyncSession, config_id: int) -> LLMConfig:
    """Load LLMConfig from database."""
    result = await db.execute(
        select(LLMConfig).where(LLMConfig.id == config_id)
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise ValueError(f"LLMConfig {config_id} not found")
    return config


def _load_system_prompt() -> str:
    """Load the visual assert system prompt from markdown file."""
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("Prompt template not found at %s, using fallback", _PROMPT_PATH)
        return _FALLBACK_PROMPT


_FALLBACK_PROMPT = (
    "You are a visual QA inspector. Analyze the screenshot against the "
    "given expectation. Return ONLY JSON: "
    '{"pass": bool, "confidence": float, "reason": str, "bboxes": []}'
)


async def _call_and_parse(
    provider,
    messages: list[Message],
    images: list[ImageRef],
) -> VisualResult:
    """Call provider.vision() and parse the JSON response.

    On parse failure, retry once. On second failure, return a
    degraded result with just pass/reason extracted heuristically.
    """
    for attempt in range(2):
        try:
            chat_result = await provider.vision(
                messages=messages,
                images=images,
                temperature=0.0,
                max_tokens=1024,
            )
            parsed = _parse_json_response(chat_result.content)
            return _build_visual_result(parsed)
        except _ParseError as exc:
            logger.warning(
                "Visual assert parse failed (attempt %d): %s",
                attempt + 1,
                exc,
            )
            if attempt == 0:
                # Retry with a stronger hint
                messages = list(messages) + [
                    Message(
                        role="user",
                        content="Your previous response was not valid JSON. "
                        "Please respond with ONLY the JSON object, "
                        'no markdown fences or extra text.',
                    ),
                ]
            else:
                # Degraded fallback
                return _degraded_result(chat_result.content if 'chat_result' in dir() else str(exc))

    # Should not reach here
    return VisualResult(passed=False, confidence=0.0, reason="Unexpected error")


class _ParseError(Exception):
    pass


def _parse_json_response(text: str) -> dict:
    """Parse JSON from the LLM response text.

    Handles common issues:
    - Markdown code fences (```json ... ```)
    - Leading/trailing whitespace
    - Extra text before/after JSON
    """
    # Strip markdown code fences
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    # Try direct parse
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the text
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            data = json.loads(brace_match.group())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    raise _ParseError(f"Could not extract JSON from response: {text[:200]}")


def _build_visual_result(data: dict) -> VisualResult:
    """Build VisualResult from parsed JSON dict."""
    passed = bool(data.get("pass", False))
    confidence = float(data.get("confidence", 0.5))
    confidence = max(0.0, min(1.0, confidence))
    reason = str(data.get("reason", ""))

    bboxes = []
    for b in data.get("bboxes", []):
        try:
            bboxes.append(BBox(
                label=str(b.get("label", "")),
                x=int(b.get("x", 0)),
                y=int(b.get("y", 0)),
                w=int(b.get("w", 0)),
                h=int(b.get("h", 0)),
            ))
        except (TypeError, ValueError):
            continue

    return VisualResult(passed=passed, confidence=confidence, reason=reason, bboxes=bboxes)


def _degraded_result(raw_text: str) -> VisualResult:
    """Build a degraded VisualResult when JSON parsing fails twice.

    Heuristic: look for pass/fail keywords in the raw text.
    """
    text_lower = raw_text.lower()
    # Heuristic pass/fail detection
    if "pass" in text_lower and "fail" not in text_lower:
        passed = True
    elif "fail" in text_lower:
        passed = False
    else:
        passed = False

    return VisualResult(
        passed=passed,
        confidence=0.3,
        reason=f"[Degraded] Could not parse structured result. Raw: {raw_text[:300]}",
        bboxes=[],
    )


async def _draw_annotated(
    screenshot_path: str,
    bboxes: list[BBox],
    *,
    run_id: int | None,
    step_index: int | None,
) -> Path | None:
    """Draw bboxes on the screenshot and save annotated image.

    Uses Pillow to draw rectangles and labels.
    Returns the output path, or None if Pillow is not available.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        logger.warning("Pillow not installed; skipping annotated image")
        return None

    if not bboxes:
        return None

    # Load original image
    try:
        img = Image.open(screenshot_path)
    except Exception as exc:
        logger.warning("Cannot open screenshot for annotation: %s", exc)
        return None

    draw = ImageDraw.Draw(img)

    # Try to get a font, fall back to default
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    except (IOError, OSError):
        font = ImageFont.load_default()

    for bbox in bboxes:
        # Draw rectangle
        rect = [bbox.x, bbox.y, bbox.x + bbox.w, bbox.y + bbox.h]
        outline_color = (255, 0, 0) if not bbox.label.startswith("ok") else (0, 200, 0)
        draw.rectangle(rect, outline=outline_color, width=3)

        # Draw label
        label_pos = (bbox.x, max(0, bbox.y - 20))
        draw.text(label_pos, bbox.label, fill=outline_color, font=font)

    # Save annotated image
    if run_id is not None and step_index is not None:
        out_dir = _STORAGE_DIR / str(run_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{step_index}_annot.png"
    else:
        _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        out_path = _STORAGE_DIR / "annotated.png"

    img.save(str(out_path))
    return out_path
