"""AI-powered failure diagnosis for test steps.

Builds context (screenshots, DOM, logs), calls vision LLM, parses structured
JSON output, and persists the result into step_diagnosis.payload_json.
"""
from __future__ import annotations

import base64
import json
import logging
import re
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import get_provider, Message, ImageRef
from app.llm.schemas import ChatResult
from app.models.llm_config import LLMConfig
from app.models.run import Run
from app.models.run_step import RunStep, StepStatus
from app.models.step_diagnosis import StepDiagnosis
from app.models.test_case import TestCase
from app.engine.step_capturer import load_step_details

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "failure_diagnose.md"

# ── Public API ──


async def diagnose_with_ai(
    db: AsyncSession,
    run_id: int,
    step_index: int,
    llm_config_id: int | None = None,
) -> StepDiagnosis:
    """Run AI diagnosis for a failed step and persist the result.

    Args:
        db: Database session
        run_id: Run ID
        step_index: Failed step index
        llm_config_id: Optional LLM config ID. Uses default if not provided.

    Returns:
        The updated StepDiagnosis row.
    """
    # 1. Load LLM config
    config = await _load_llm_config(db, llm_config_id)
    provider = get_provider(config)

    # 2. Gather context
    context = await _build_context(db, run_id, step_index)

    # 3. Load prompt and build messages
    system_prompt = _load_system_prompt()
    user_prompt = _build_user_prompt(context)

    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=user_prompt),
    ]

    # 4. Build image refs (failure screenshot + prev step screenshot if any)
    images = []
    failure_b64 = _image_to_base64(context["failure_screenshot_path"])
    if failure_b64:
        images.append(ImageRef(type="base64", data=failure_b64, media_type="image/png"))
    prev_b64 = _image_to_base64(context.get("prev_screenshot_path"))
    if prev_b64:
        images.append(ImageRef(type="base64", data=prev_b64, media_type="image/png"))

    # 5. Call LLM
    chat_result = await provider.vision(
        messages=messages,
        images=images,
        temperature=0.2,
        max_tokens=4096,
    )

    # 6. Parse JSON
    ai_result = _parse_ai_response(chat_result.content)

    # 7. Persist into step_diagnosis.payload_json.ai_diagnosis
    diagnosis = await _upsert_ai_diagnosis(db, run_id, step_index, ai_result)

    return diagnosis


# ── Context building ──


async def _build_context(
    db: AsyncSession, run_id: int, step_index: int
) -> dict[str, Any]:
    """Gather all relevant context for the failed step."""
    context: dict[str, Any] = {
        "run_id": run_id,
        "step_index": step_index,
    }

    # Run info
    run_result = await db.execute(select(Run).where(Run.id == run_id))
    run = run_result.scalar_one()
    context["run"] = {"id": run.id, "status": run.status.value}

    # Test case steps
    tc_result = await db.execute(select(TestCase).where(TestCase.id == run.test_case_id))
    test_case = tc_result.scalar_one()
    context["test_case"] = {"id": test_case.id, "name": test_case.name, "steps": test_case.steps_json}

    # Failed step
    step_result = await db.execute(
        select(RunStep)
        .where(RunStep.run_id == run_id, RunStep.step_index == step_index)
    )
    step = step_result.scalar_one()
    context["failed_step"] = {
        "action": step.action,
        "input_json": step.input_json,
        "error": step.error,
        "status": step.status.value,
        "screenshot_path": step.screenshot_path,
    }
    context["failure_screenshot_path"] = _resolve_screenshot_path(step.screenshot_path, run_id, step_index)

    # Previous step (successful)
    if step_index > 0:
        prev_result = await db.execute(
            select(RunStep)
            .where(RunStep.run_id == run_id, RunStep.step_index == step_index - 1)
        )
        prev_step = prev_result.scalar_one_or_none()
        if prev_step and prev_step.status == StepStatus.passed:
            context["prev_step"] = {
                "action": prev_step.action,
                "status": prev_step.status.value,
                "screenshot_path": prev_step.screenshot_path,
            }
            context["prev_screenshot_path"] = _resolve_screenshot_path(
                prev_step.screenshot_path, run_id, step_index - 1
            )

    # Step details (console logs, network, DOM)
    details = load_step_details(run_id, step_index)
    if details:
        context["details"] = {
            "console_logs": details.console_logs,
            "network_requests": details.network_requests,
            "dom_snippet": details.dom_snippet,
            "target_bbox": details.target_bbox,
        }
        # Filter console errors
        context["console_errors"] = [
            log for log in details.console_logs if log.get("type") == "error"
        ]
        # Filter network errors (4xx/5xx or no response)
        context["network_errors"] = [
            req for req in details.network_requests
            if _is_network_error(req)
        ]

    # Existing rule-based diagnosis (if any)
    diag_result = await db.execute(
        select(StepDiagnosis)
        .where(StepDiagnosis.run_id == run_id, StepDiagnosis.step_index == step_index)
    )
    existing = diag_result.scalar_one_or_none()
    if existing and existing.payload_json:
        payload = existing.payload_json
        context["rule_diagnosis"] = {
            "error_type": payload.get("summary", {}).get("error_type"),
            "dom_exists": payload.get("context", {}).get("dom_exists"),
            "dom_visible": payload.get("context", {}).get("dom_visible"),
            "candidate_selectors": payload.get("fixes", {}).get("candidate_selectors", []),
            "suggest_wait": payload.get("fixes", {}).get("suggest_wait"),
            "suggest_scroll": payload.get("fixes", {}).get("suggest_scroll"),
        }

    return context


def _resolve_screenshot_path(screenshot_path: str | None, run_id: int, step_index: int) -> str | None:
    """Resolve screenshot path to an absolute filesystem path."""
    if screenshot_path:
        # screenshot_path may be a URL like /screenshots/1/2_after.png
        if screenshot_path.startswith("/"):
            return str(Path("storage") / screenshot_path.lstrip("/"))
        return screenshot_path
    # Fallback: try standard naming
    fallback = Path(f"storage/screenshots/{run_id}/{step_index}_after.png")
    if fallback.exists():
        return str(fallback)
    return None


def _image_to_base64(path: str | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = p.read_bytes()
        return base64.b64encode(data).decode("utf-8")
    except Exception:
        logger.warning("Failed to read screenshot: %s", path)
        return None


def _is_network_error(req: dict) -> bool:
    resp = req.get("response")
    if not resp:
        return True  # No response = pending/error
    status = resp.get("status", 0)
    return status >= 400


# ── Prompt building ──


def _load_system_prompt() -> str:
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding="utf-8")
    logger.warning("Prompt not found at %s, using fallback", _PROMPT_PATH)
    return _FALLBACK_PROMPT


_FALLBACK_PROMPT = (
    "You are a web automation debugging expert. "
    "Given a failed test step, screenshots, and context, diagnose the root cause "
    "and suggest a minimal fix. Output ONLY a JSON object with fields: "
    "root_cause, explanation, suggested_fix (with type and new_steps_patch), confidence."
)


def _build_user_prompt(context: dict[str, Any]) -> str:
    """Build user prompt from gathered context."""
    parts = []

    # Test case overview
    tc = context["test_case"]
    parts.append(f"## Test Case: {tc['name']}")
    parts.append(f"## Total Steps: {len(tc['steps'])}")

    # Failed step
    failed = context["failed_step"]
    parts.append(f"\n## Failed Step (index {context['step_index']})")
    parts.append(f"- action: {failed['action']}")
    if failed.get("input_json"):
        parts.append(f"- params: {json.dumps(failed['input_json'], ensure_ascii=False)}")
    parts.append(f"- error: {failed['error']}")

    # Previous step
    if "prev_step" in context:
        prev = context["prev_step"]
        parts.append(f"\n## Previous Step (index {context['step_index'] - 1})")
        parts.append(f"- action: {prev['action']}")
        parts.append(f"- status: {prev['status']}")

    # DOM snippet
    details = context.get("details", {})
    if details.get("dom_snippet"):
        parts.append(f"\n## Target Element DOM\n```html\n{details['dom_snippet'][:2000]}\n```")

    # Console errors
    console_errors = context.get("console_errors", [])
    if console_errors:
        parts.append(f"\n## Console Errors ({len(console_errors)})")
        for log in console_errors[:10]:
            parts.append(f"- [{log.get('type')}] {log.get('text', '')[:200]}")

    # Network errors
    network_errors = context.get("network_errors", [])
    if network_errors:
        parts.append(f"\n## Network Errors ({len(network_errors)})")
        for req in network_errors[:10]:
            status = req.get("response", {}).get("status", "no response")
            parts.append(f"- [{status}] {req.get('method', '?')} {req.get('url', '')[:120]}")

    # Rule-based diagnosis reference
    if "rule_diagnosis" in context:
        rd = context["rule_diagnosis"]
        parts.append(f"\n## Rule-based Diagnosis (reference)")
        parts.append(f"- error_type: {rd.get('error_type')}")
        parts.append(f"- dom_exists: {rd.get('dom_exists')}")
        parts.append(f"- dom_visible: {rd.get('dom_visible')}")
        parts.append(f"- suggest_wait: {rd.get('suggest_wait')}")
        parts.append(f"- suggest_scroll: {rd.get('suggest_scroll')}")
        if rd.get("candidate_selectors"):
            parts.append("- candidate selectors:")
            for c in rd["candidate_selectors"][:5]:
                parts.append(f"  - {c.get('selector')} (confidence: {c.get('confidence')})")

    # All steps for context
    parts.append(f"\n## Full Test Case Steps\n```json\n{json.dumps(tc['steps'], ensure_ascii=False, indent=2)}\n```")

    parts.append("\n## Your Task\nAnalyze the failure and output the diagnosis JSON.")

    return "\n".join(parts)


# ── LLM response parsing ──


def _parse_ai_response(text: str) -> dict[str, Any]:
    """Extract and validate JSON from LLM response."""
    text = text.strip()

    # Strip markdown fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    # Try direct parse
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            _validate_ai_result(data)
            return data
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in text
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            data = json.loads(brace_match.group())
            if isinstance(data, dict):
                _validate_ai_result(data)
                return data
        except (json.JSONDecodeError, ValueError):
            pass

    logger.warning("Could not parse AI diagnosis JSON from: %s", text[:500])
    return _fallback_result(text)


def _validate_ai_result(data: dict) -> None:
    """Validate the AI result structure."""
    required_top = ["root_cause", "explanation", "suggested_fix", "confidence"]
    for key in required_top:
        if key not in data:
            raise ValueError(f"Missing required field: {key}")

    fix = data["suggested_fix"]
    if not isinstance(fix, dict):
        raise ValueError("suggested_fix must be an object")
    if "type" not in fix:
        raise ValueError("suggested_fix missing 'type'")
    if "new_steps_patch" not in fix:
        raise ValueError("suggested_fix missing 'new_steps_patch'")
    if not isinstance(fix["new_steps_patch"], list):
        raise ValueError("new_steps_patch must be an array")

    for i, op in enumerate(fix["new_steps_patch"]):
        if not isinstance(op, dict):
            raise ValueError(f"patch[{i}] must be an object")
        if "op" not in op or "step_index" not in op:
            raise ValueError(f"patch[{i}] missing 'op' or 'step_index'")
        if op["op"] not in ("replace", "insert", "delete"):
            raise ValueError(f"patch[{i}] invalid op: {op['op']}")
        if op["op"] in ("replace", "insert") and "step" not in op:
            raise ValueError(f"patch[{i}] ({op['op']}) missing 'step'")


def _fallback_result(raw_text: str) -> dict[str, Any]:
    """Return a fallback result when parsing fails."""
    return {
        "root_cause": "other",
        "explanation": f"AI 返回无法解析。原始输出:\n{raw_text[:500]}",
        "suggested_fix": {
            "type": "other",
            "new_steps_patch": [],
        },
        "confidence": 0.0,
    }


# ── Persistence ──


async def _upsert_ai_diagnosis(
    db: AsyncSession, run_id: int, step_index: int, ai_result: dict[str, Any]
) -> StepDiagnosis:
    """Update existing StepDiagnosis row or create a new one with ai_diagnosis in payload."""
    result = await db.execute(
        select(StepDiagnosis)
        .where(StepDiagnosis.run_id == run_id, StepDiagnosis.step_index == step_index)
    )
    diagnosis = result.scalar_one_or_none()

    if diagnosis is None:
        # Create new diagnosis with both rule and AI parts
        payload = {
            "summary": {
                "action": "unknown",
                "error_text": "",
                "error_type": "UnknownError",
                "selector": None,
                "step_index": step_index,
            },
            "context": {},
            "visual_diff": {},
            "fixes": {},
            "ai_diagnosis": ai_result,
            "generated_at": "",
        }
        diagnosis = StepDiagnosis(
            run_id=run_id,
            step_index=step_index,
            payload_json=payload,
        )
        db.add(diagnosis)
    else:
        # Update existing payload
        payload = dict(diagnosis.payload_json or {})
        payload["ai_diagnosis"] = ai_result
        diagnosis.payload_json = payload

    await db.flush()
    await db.refresh(diagnosis)
    return diagnosis


# ── LLM Config ──


async def _load_llm_config(db: AsyncSession, config_id: int | None) -> LLMConfig:
    if config_id is not None:
        result = await db.execute(select(LLMConfig).where(LLMConfig.id == config_id))
        cfg = result.scalar_one_or_none()
        if cfg:
            return cfg
        logger.warning("LLMConfig %s not found, using default", config_id)

    result = await db.execute(select(LLMConfig).where(LLMConfig.is_default == True))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        raise ValueError("No default LLM config found. Please configure one.")
    return cfg
