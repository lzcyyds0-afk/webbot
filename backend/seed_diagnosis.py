"""Seed script: insert fake step_diagnosis records for failed steps.

Usage:
    PYTHONPATH=. uv run python seed_diagnosis.py
"""
import asyncio
from datetime import datetime, timezone

from app.core.database import async_session
from app.models.run_step import RunStep, StepStatus
from app.models.step_diagnosis import StepDiagnosis
from app.models.run import Run, RunStatus
from sqlalchemy import select


async def seed_diagnoses() -> None:
    async with async_session() as session:
        # Find all failed steps without a diagnosis
        result = await session.execute(
            select(RunStep)
            .where(RunStep.status == StepStatus.failed)
            .order_by(RunStep.run_id, RunStep.step_index)
        )
        failed_steps = result.scalars().all()

        if not failed_steps:
            print("No failed steps found in database.")
            return

        # Find a baseline passed run for visual diff
        baseline_result = await session.execute(
            select(Run)
            .where(Run.status == RunStatus.passed)
            .order_by(Run.started_at.desc())
            .limit(1)
        )
        baseline_run = baseline_result.scalar_one_or_none()

        inserted = 0
        for step in failed_steps:
            # Skip if diagnosis already exists
            existing = await session.execute(
                select(StepDiagnosis)
                .where(
                    StepDiagnosis.run_id == step.run_id,
                    StepDiagnosis.step_index == step.step_index,
                )
            )
            if existing.scalar_one_or_none():
                print(f"Skipping run={step.run_id} step={step.step_index} (already has diagnosis)")
                continue

            # Get run info for baseline lookup
            run_result = await session.execute(
                select(Run).where(Run.id == step.run_id)
            )
            run = run_result.scalar_one()

            # Find baseline step for same test_case and step_index
            baseline_step_info = None
            if baseline_run and baseline_run.test_case_id == run.test_case_id:
                baseline_step_result = await session.execute(
                    select(RunStep)
                    .where(
                        RunStep.run_id == baseline_run.id,
                        RunStep.step_index == step.step_index,
                    )
                )
                baseline_step = baseline_step_result.scalar_one_or_none()
                if baseline_step and baseline_step.screenshot_path:
                    baseline_step_info = {
                        "run_id": baseline_run.id,
                        "screenshot_url": baseline_step.screenshot_path,
                        "run_started_at": (
                            baseline_run.started_at.isoformat()
                            if baseline_run.started_at
                            else None
                        ),
                    }

            selector = step.input_json.get("selector") if step.input_json else None
            error_text = step.error or "Unknown error"
            error_type = "TimeoutError"
            if "selector" in error_text.lower() or "locator" in error_text.lower():
                error_type = "SelectorError"
            elif "navigation" in error_text.lower() or "goto" in error_text.lower():
                error_type = "NavigationError"
            elif "visible" in error_text.lower():
                error_type = "VisibilityError"
            elif "detached" in error_text.lower() or "stale" in error_text.lower():
                error_type = "StaleElementError"

            payload = {
                "summary": {
                    "action": step.action,
                    "error_text": error_text,
                    "error_type": error_type,
                    "selector": selector,
                    "step_index": step.step_index,
                },
                "context": {
                    "screenshot_url": step.screenshot_path or f"/screenshots/{step.run_id}/{step.step_index}_after.png",
                    "dom_exists": error_type != "SelectorError",
                    "dom_visible": False,
                    "dom_obscured": error_type == "TimeoutError",
                    "viewport_info": {
                        "width": 1920,
                        "height": 1080,
                        "scroll_x": 0,
                        "scroll_y": 0,
                    },
                    "page_url": "https://example.com/dashboard",
                    "page_title": "Dashboard - Example App",
                    "expected_url": None,
                },
                "visual_diff": {
                    "has_baseline": baseline_step_info is not None,
                    "baseline_run_id": baseline_step_info["run_id"] if baseline_step_info else None,
                    "baseline_screenshot_url": baseline_step_info["screenshot_url"] if baseline_step_info else None,
                    "baseline_run_started_at": baseline_step_info["run_started_at"] if baseline_step_info else None,
                    "current_screenshot_url": step.screenshot_path or f"/screenshots/{step.run_id}/{step.step_index}_after.png",
                    "diff_note": (
                        "目标元素在 DOM 中未找到，可能是 selector 失效或页面未加载完成"
                        if error_type == "SelectorError"
                        else "元素存在于 DOM 中但不可见，可能被隐藏或需要等待动画"
                        if error_type == "TimeoutError"
                        else "操作执行失败，请查看截图和 DOM 快照"
                    ),
                },
                "fixes": {
                    "candidate_selectors": [
                        {
                            "selector": "button[data-testid='submit-btn']",
                            "confidence": 0.85,
                            "reason": "同 tag(button) + 相似 data-testid",
                            "found_count": 1,
                        },
                        {
                            "selector": "button:has-text('提交')",
                            "confidence": 0.72,
                            "reason": "同 tag(button) + 相似文本",
                            "found_count": 2,
                        },
                        {
                            "selector": "button.primary",
                            "confidence": 0.55,
                            "reason": "同 tag(button) + 相似 class",
                            "found_count": 3,
                        },
                    ] if selector else [],
                    "suggest_wait": error_type == "TimeoutError",
                    "suggest_scroll": False,
                    "suggest_retry": error_type == "StaleElementError",
                },
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

            diagnosis = StepDiagnosis(
                run_id=step.run_id,
                step_index=step.step_index,
                payload_json=payload,
            )
            session.add(diagnosis)
            inserted += 1
            print(f"Prepared diagnosis for run={step.run_id} step={step.step_index}")

        await session.commit()
        print(f"Inserted {inserted} diagnosis record(s).")


async def main() -> None:
    await seed_diagnoses()


if __name__ == "__main__":
    asyncio.run(main())
