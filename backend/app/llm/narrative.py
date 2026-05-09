"""Generate human-readable narrative summaries for test runs."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.run import Run, RunStatus
from app.models.run_step import RunStep
from app.models.test_case import TestCase
from app.models.llm_config import LLMConfig
from app.llm import get_provider, Message

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "narrative.md"


class NarrativeResult(BaseModel):
    summary: str
    process: str
    conclusion: str


def _load_prompt() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("Narrative prompt not found at %s, using fallback", _PROMPT_PATH)
        return _FALLBACK_PROMPT


_FALLBACK_PROMPT = (
    "你是一个 Web 自动化测试分析师。请根据测试执行记录生成 JSON 格式的报告，"
    "包含 summary（20字内）、process（过程叙述）、conclusion（结论建议）三个字段。"
    "不要输出 markdown 围栏。"
)


def _parse_narrative_json(text: str) -> NarrativeResult | None:
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
        return NarrativeResult(
            summary=str(data.get("summary", ""))[:120],
            process=str(data.get("process", ""))[:3000],
            conclusion=str(data.get("conclusion", ""))[:1500],
        )
    except Exception as exc:
        logger.warning("Failed to parse narrative JSON: %s. Raw: %s", exc, text[:300])
        return None


async def generate_run_narrative(db: AsyncSession, run_id: int) -> NarrativeResult | None:
    """Generate a narrative summary for a completed run and persist it."""
    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        logger.warning("Run %s not found for narrative generation", run_id)
        return None

    steps_result = await db.execute(
        select(RunStep).where(RunStep.run_id == run_id).order_by(RunStep.step_index)
    )
    steps = steps_result.scalars().all()
    if not steps:
        logger.warning("Run %s has no steps, skipping narrative", run_id)
        return None

    # Load test case name
    tc_result = await db.execute(select(TestCase).where(TestCase.id == run.test_case_id))
    tc = tc_result.scalar_one_or_none()
    case_name = tc.name if tc else "未命名用例"

    # Load default LLM config (fallback to first available)
    llm_result = await db.execute(select(LLMConfig).where(LLMConfig.is_default.is_(True)))
    config = llm_result.scalar_one_or_none()
    if not config:
        llm_result = await db.execute(select(LLMConfig).limit(1))
        config = llm_result.scalar_one_or_none()
    if not config:
        logger.warning("No LLM config available for narrative generation")
        return None

    provider = get_provider(config)

    # Build step execution log
    step_lines: list[str] = []
    url_history: list[str] = []
    for s in steps:
        parts: list[str] = [f"#{s.step_index} {s.action}"]
        if s.input_json:
            params = {k: v for k, v in s.input_json.items() if not k.startswith("_")}
            if params:
                params_str = ", ".join(f"{k}={v}" for k, v in params.items())
                parts.append(f"params=({params_str})")
        if s.output_json:
            url = s.output_json.get("url")
            if url and url not in url_history:
                url_history.append(url)
                parts.append(f"-> url={url}")
            title = s.output_json.get("title")
            if title:
                parts.append(f"-> title={title}")
            if s.output_json.get("healed"):
                parts.append(
                    f"[self-healed: {s.output_json.get('healed_selector', '?')}]"
                )
        parts.append(f"status={s.status.value}")
        if s.duration_ms is not None:
            parts.append(f"duration={s.duration_ms}ms")
        if s.error:
            # Truncate very long errors
            err = s.error if len(s.error) <= 200 else s.error[:200] + "..."
            parts.append(f"ERROR: {err}")
        step_lines.append(" | ".join(parts))

    steps_text = "\n".join(step_lines)

    total = len(steps)
    passed = sum(1 for s in steps if s.status.value == "passed")
    failed = sum(1 for s in steps if s.status.value == "failed")

    duration_text = "N/A"
    if run.started_at and run.finished_at:
        duration_text = f"{(run.finished_at - run.started_at).total_seconds():.1f}s"

    user_content = (
        f"## 测试用例\n{case_name}\n\n"
        f"## 执行结果\n状态: {run.status.value}\n"
        f"总步骤: {total}\n通过: {passed}\n失败: {failed}\n"
        f"总耗时: {duration_text}\n\n"
        f"## 步骤执行日志\n{steps_text}\n\n"
        "请输出 JSON 格式的测试故事报告。"
    )

    messages = [
        Message(role="system", content=_load_prompt()),
        Message(role="user", content=user_content),
    ]

    try:
        chat_result = await provider.chat(
            messages=messages,
            temperature=0.3,
            max_tokens=1024,
        )
    except Exception:
        logger.exception("LLM chat failed for narrative generation run=%s", run_id)
        return None

    raw = chat_result.content
    narrative = _parse_narrative_json(raw)
    if narrative is None:
        logger.warning("Could not parse narrative from LLM output for run=%s", run_id)
        return None

    # Persist to DB
    run.narrative = narrative.model_dump_json()
    from datetime import datetime, timezone
    run.narrative_generated_at = datetime.now(timezone.utc)
    await db.flush()

    logger.info("Narrative generated for run=%s", run_id)
    return narrative
