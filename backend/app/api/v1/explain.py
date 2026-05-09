"""AI Preview (预演) API: explain what each test step will do before running."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.engine.browser import BrowserManager
from app.engine.self_heal import _extract_visible_elements
from app.llm import get_provider, Message
from app.models.llm_config import LLMConfig
from app.models.project import Project
from app.models.test_case import TestCase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects/{project_id}/test-cases", tags=["explain"])

_PROMPT_PATH = Path(__file__).parent.parent.parent / "llm" / "prompts" / "test_case_explain.md"

# ── Schemas ──


class StepExplanation(BaseModel):
    step_index: int
    action: str
    intent: str
    prediction: str
    risk: str
    risk_level: str  # low | medium | high
    confidence: float


class TestCaseExplainOut(BaseModel):
    case_id: int
    overall_risk: str  # low | medium | high
    overall_advice: str
    steps: list[StepExplanation]


# ── Helpers ──


def _load_system_prompt() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("Prompt template not found at %s, using fallback", _PROMPT_PATH)
        return _FALLBACK_SYSTEM


_FALLBACK_SYSTEM = (
    "你是 Web 自动化测试审计员。根据测试步骤预判每一步会发生什么、风险在哪。"
    "输出 JSON：overall_risk, overall_advice, steps（含 step_index, intent, prediction, risk, risk_level, confidence）。"
    "risk_level 取 low/medium/high。intent 和 prediction 用中文。"
)


def _find_first_url(steps: list[dict]) -> str | None:
    """Extract the first goto URL from steps."""
    for step in steps:
        if isinstance(step, dict) and step.get("action") == "goto":
            url = step.get("url")
            if url and isinstance(url, str):
                return url
    return None


async def _capture_page_summary(url: str) -> dict | None:
    """Open URL and extract visible element summary without taking screenshot."""
    bm = BrowserManager(headless=True)
    try:
        await bm.start()
        page = await bm.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=10_000)
        await page.wait_for_timeout(1000)
        elements = await _extract_visible_elements(page, max_items=30)
        return {"url": url, "elements": elements}
    except Exception as exc:
        logger.debug("Page capture failed for %s: %s", url, exc)
        return None
    finally:
        try:
            await bm.close()
        except Exception:
            pass


def _build_user_prompt(steps: list[dict], page_summary: dict | None) -> str:
    parts = ["## 测试步骤", json.dumps(steps, ensure_ascii=False, indent=2)]
    if page_summary and page_summary.get("elements"):
        parts.append("## 页面可见元素摘要")
        for el in page_summary["elements"]:
            line = f"- [{el.get('tag', '?')}] text={el.get('text', '')!r} selector={el.get('selector', '')}"
            if el.get("data_testid"):
                line += f" data-testid={el['data_testid']!r}"
            if el.get("aria_label"):
                line += f" aria-label={el['aria_label']!r}"
            parts.append(line)
    else:
        parts.append("## 页面上下文\n（无法抓取页面，仅基于步骤内容分析）")
    return "\n".join(parts)


def _parse_explain_json(text: str) -> dict:
    """Parse LLM response into a dict."""
    text = text.strip()
    # Strip markdown fences
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
    raise ValueError(f"Could not extract JSON object from response: {text[:300]}")


async def _get_default_llm_config(db: AsyncSession) -> LLMConfig | None:
    result = await db.execute(select(LLMConfig).where(LLMConfig.is_default == True))
    cfg = result.scalar_one_or_none()
    if cfg:
        return cfg
    # Fallback to first config
    result = await db.execute(select(LLMConfig).order_by(LLMConfig.id))
    return result.scalars().first()


# ── Endpoint ──


@router.post("/{case_id}/explain", response_model=TestCaseExplainOut)
async def explain_test_case(
    project_id: int,
    case_id: int,
    db: AsyncSession = Depends(get_db),
):
    # Verify project exists
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    if proj_result.scalar_one_or_none() is None:
        raise HTTPException(404, "Project not found")

    # Load test case
    tc_result = await db.execute(
        select(TestCase).where(TestCase.id == case_id, TestCase.project_id == project_id)
    )
    tc = tc_result.scalar_one_or_none()
    if tc is None:
        raise HTTPException(404, "Test case not found")

    steps = tc.steps_json if isinstance(tc.steps_json, list) else []

    # Capture page summary if first goto URL is present
    first_url = _find_first_url(steps)
    page_summary = None
    if first_url:
        page_summary = await _capture_page_summary(first_url)

    # Load default LLM config
    config = await _get_default_llm_config(db)
    if config is None:
        raise HTTPException(503, "No LLM config available")

    provider = get_provider(config)

    # Build prompt
    system_prompt = _load_system_prompt()
    user_prompt = _build_user_prompt(steps, page_summary)

    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=user_prompt),
    ]

    # Call LLM
    try:
        chat_result = await provider.chat(
            messages=messages,
            temperature=0.2,
            max_tokens=4096,
        )
    except Exception as exc:
        logger.error("LLM explain failed: %s", exc)
        raise HTTPException(502, f"LLM call failed: {exc}")

    # Parse response
    try:
        parsed = _parse_explain_json(chat_result.content)
    except ValueError as exc:
        logger.error("Failed to parse LLM explain response: %s", exc)
        raise HTTPException(502, f"Invalid LLM response format: {exc}")

    raw_steps = parsed.get("steps", [])
    result_steps: list[StepExplanation] = []
    for i, raw in enumerate(raw_steps):
        result_steps.append(
            StepExplanation(
                step_index=raw.get("step_index", i),
                action=steps[raw.get("step_index", i)].get("action", "") if raw.get("step_index", i) < len(steps) else "",
                intent=raw.get("intent", ""),
                prediction=raw.get("prediction", ""),
                risk=raw.get("risk", "无显著风险"),
                risk_level=raw.get("risk_level", "low"),
                confidence=float(raw.get("confidence", 0.8)),
            )
        )

    return TestCaseExplainOut(
        case_id=case_id,
        overall_risk=parsed.get("overall_risk", "low"),
        overall_advice=parsed.get("overall_advice", ""),
        steps=result_steps,
    )
