from __future__ import annotations
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.engine.browser import get_shared_browser
from app.engine.actions import ActionExecutor
from app.engine.storage import Storage
from app.engine.ws_broadcaster import WsBroadcaster, NullBroadcaster
from app.engine.models import StepContext, WsMessage
from app.engine.step_capturer import StepCapturer, persist_step_details
from app.engine.self_heal import SelfHealEngine, record_heal_event

from app.models.test_case import TestCase
from app.models.run import Run, RunStatus
from app.models.run_step import RunStep, StepStatus

logger = logging.getLogger(__name__)


class Runner:
    def __init__(
        self,
        db: AsyncSession,
        broadcaster: WsBroadcaster | None = None,
    ) -> None:
        self._db = db
        self._broadcaster = broadcaster or NullBroadcaster()
        self._heal_engine = SelfHealEngine(db=db)
        self._executor = ActionExecutor(heal_engine=self._heal_engine)
        self._storage = Storage()
        self._capturer = StepCapturer()

    async def run(self, case: TestCase, run_id: int | None = None) -> Run:
        if run_id is not None:
            # Load existing run
            result = await self._db.execute(select(Run).where(Run.id == run_id))
            run = result.scalar_one_or_none()
            if not run:
                raise ValueError(f"Run {run_id} not found")
            run.status = RunStatus.running
            run.started_at = datetime.now(timezone.utc)
        else:
            run = Run(
                test_case_id=case.id,
                status=RunStatus.running,
                started_at=datetime.now(timezone.utc),
            )
        self._db.add(run)
        await self._db.flush()

        page = None
        run_failed = False

        try:
            # Reuse the shared browser; this run gets its own isolated context.
            bm = await get_shared_browser()
            # Pass cookies from test case if available
            cookies = case.cookies_json if case.cookies_json else None
            page = await bm.new_page(cookies=cookies)
            await self._capturer.setup(page)

            # Cap total wall-clock time: every action already has its own
            # timeout, so we just stop launching new steps once the run budget
            # is exhausted, preventing a runaway test from holding the browser.
            run_started = time.monotonic()

            for i, step_def in enumerate(case.steps_json):
                if time.monotonic() - run_started > settings.run_timeout_seconds:
                    logger.warning(
                        "Run %s exceeded time budget of %ss; stopping",
                        run.id, settings.run_timeout_seconds,
                    )
                    run_failed = True
                    break

                action = step_def.get("action", "")
                params = {k: v for k, v in step_def.items() if k != "action"}
                ctx = StepContext(
                    run_id=run.id,
                    step_index=i,
                    action=action,
                    params=params,
                    base_url=case.project.base_url if case.project else "",
                )

                # ── before screenshot ──
                before_path = self._storage.screenshot_path(run.id, i, suffix="")
                before_url = f"/screenshots/{run.id}/{i}.png"
                try:
                    await self._storage.save_screenshot(page, before_path)
                except Exception:
                    logger.warning("Before screenshot failed for run=%s step=%s", run.id, i)
                    before_url = None

                # ── start capturing ──
                self._capturer.start_step()
                # Try to capture target element info before action
                target_selector = params.get("selector") or params.get("from_selector")
                if target_selector:
                    try:
                        await self._capturer.capture_target(target_selector)
                    except Exception:
                        pass

                # ── push step_start ──
                await self._broadcaster.emit(WsMessage(
                    event="step_start",
                    run_id=run.id,
                    step_index=i,
                    status="running",
                    screenshot_url=before_url,
                    action=action,
                    params_summary=_params_summary(params),
                    screenshot_before=before_url,
                ))

                # ── execute action ──
                result = await self._executor.execute(page, ctx)

                # ── if healed, record event and notify ──
                output = result.output_json or {}
                if output.get("healed"):
                    try:
                        await record_heal_event(
                            self._db,
                            run_id=run.id,
                            step_index=i,
                            original_selector=output.get("_original_selector", ""),
                            healed_selector=output.get("healed_selector", ""),
                            method=output.get("_heal_method", "rule"),
                        )
                        await self._broadcaster.emit(WsMessage(
                            event="heal_notice",
                            run_id=run.id,
                            step_index=i,
                            status="healed",
                            action=action,
                            params_summary=_params_summary(params),
                            screenshot_before=before_url,
                            healed=True,
                            healed_selector=output.get("healed_selector"),
                            original_selector=output.get("_original_selector"),
                        ))
                    except Exception:
                        logger.exception("Heal event recording failed for run=%s step=%s", run.id, i)

                # ── stop capturing ──
                self._capturer.end_step()
                capture_data = self._capturer.get_data()

                # ── after screenshot ──
                # A dedicated `screenshot` step honors its `full_page` param;
                # the implicit per-step capture stays viewport-only.
                after_full_page = action == "screenshot" and bool(params.get("full_page"))
                after_path = self._storage.screenshot_path(run.id, i, suffix="_after")
                after_url: str | None = None
                try:
                    await self._storage.save_screenshot(page, after_path, full_page=after_full_page)
                    after_url = f"/screenshots/{run.id}/{i}_after.png"
                    result.screenshot_path = after_url
                except Exception:
                    logger.warning("After screenshot failed for run=%s step=%s", run.id, i)

                # ── persist step details ──
                try:
                    persist_step_details(run.id, i, capture_data)
                except Exception:
                    logger.warning("Persist step details failed for run=%s step=%s", run.id, i)

                # ── write run_steps row ──
                step_row = RunStep(
                    run_id=run.id,
                    step_index=i,
                    action=action,
                    input_json=result.input_json,
                    output_json=result.output_json,
                    screenshot_path=result.screenshot_path,
                    status=result.status,
                    duration_ms=result.duration_ms,
                    error=result.error,
                )
                self._db.add(step_row)
                await self._db.flush()

                # ── push step_end ──
                await self._broadcaster.emit(WsMessage(
                    event="step_end",
                    run_id=run.id,
                    step_index=i,
                    status=result.status.value,
                    screenshot_url=after_url,
                    error=result.error,
                    action=action,
                    params_summary=_params_summary(params),
                    duration_ms=result.duration_ms,
                    screenshot_before=before_url,
                    screenshot_after=after_url,
                    dom_snippet=capture_data.dom_snippet,
                    target_bbox=capture_data.target_bbox,
                    console_logs=capture_data.console_logs,
                    network_requests=capture_data.network_requests,
                ))

                # ── if failed, stop executing remaining steps ──
                if result.status == StepStatus.failed:
                    run_failed = True
                    # Generate diagnosis
                    from app.engine.diagnosis import diagnose_failed_step
                    try:
                        await diagnose_failed_step(page, self._db, ctx, result, capture_data)
                    except Exception:
                        logger.exception("Diagnosis generation failed for run=%s step=%s", run.id, i)
                    break

        except Exception as exc:
            logger.exception("Runner fatal error for run=%s", run.id)
            run_failed = True

        finally:
            try:
                await self._capturer.teardown()
            except Exception:
                pass
            # Close only this run's context; the browser is shared and stays up.
            if page is not None:
                try:
                    await page.context.close()
                except Exception:
                    logger.warning("Context close failed for run=%s", run.id)

        # ── finalize run ──
        run.status = RunStatus.failed if run_failed else RunStatus.passed
        run.finished_at = datetime.now(timezone.utc)
        await self._db.flush()

        # ── push run_end ──
        await self._broadcaster.emit(WsMessage(
            event="run_end",
            run_id=run.id,
            step_index=None,
            status=run.status.value,
        ))

        return run


def _params_summary(params: dict) -> str:
    """Short string representation of step params for UI display."""
    parts = []
    for k, v in params.items():
        if isinstance(v, str):
            s = v if len(v) <= 40 else v[:37] + "..."
            parts.append(f"{k}={s}")
        else:
            parts.append(f"{k}={v}")
    return ", ".join(parts)
