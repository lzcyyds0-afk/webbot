from __future__ import annotations
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.browser import BrowserManager
from app.engine.actions import ActionExecutor
from app.engine.storage import Storage
from app.engine.ws_broadcaster import WsBroadcaster, NullBroadcaster
from app.engine.models import StepContext, WsMessage
from app.engine.step_capturer import StepCapturer, persist_step_details
from app.engine.self_heal import SelfHealEngine, record_heal_event
from app.engine.auth import (
    is_likely_login_page,
    inject_storage_state,
)

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

        bm = BrowserManager()  # uses settings.headless
        page = None
        run_failed = False

        try:
            await bm.start()
            # Pass cookies from test case if available
            cookies = case.cookies_json if case.cookies_json else None
            page = await bm.new_page(cookies=cookies)
            await self._capturer.setup(page)

            # ── Storage state injection (localStorage / sessionStorage) ──
            auth = case.auth_json or {}
            local_storage = auth.get("local_storage") if isinstance(auth, dict) else None
            session_storage = auth.get("session_storage") if isinstance(auth, dict) else None
            # localStorage is per-origin, requires a page to exist. We inject lazily
            # via init_script so the first navigation picks it up.
            if local_storage or session_storage:
                try:
                    payload_js = (
                        "() => { "
                        f"const local = {_safe_json(local_storage or {})};"
                        f"const session = {_safe_json(session_storage or {})};"
                        "for (const [k,v] of Object.entries(local)) { try { window.localStorage.setItem(k,v); } catch(e){} }"
                        "for (const [k,v] of Object.entries(session)) { try { window.sessionStorage.setItem(k,v); } catch(e){} }"
                        "}"
                    )
                    await page.add_init_script(f"({payload_js})()")
                except Exception:
                    logger.warning("Failed to register storage init_script for run=%s", run.id)

            # ── Track whether we've checked cookie validity yet ──
            cookie_check_done = False

            # Pre-decrypt stored credentials (if any) for use by login steps
            stored_creds = _decrypt_stored_credentials(auth.get("credentials") if isinstance(auth, dict) else None)

            for i, step_def in enumerate(case.steps_json):
                action = step_def.get("action", "")
                params = {k: v for k, v in step_def.items() if k != "action"}

                # If login step references stored credentials (no inline username/password),
                # inject them from auth_json.credentials.
                if action == "login" and stored_creds:
                    for key in ("url", "username", "password", "username_selector",
                                "password_selector", "submit_selector", "success_url_pattern"):
                        if key not in params and stored_creds.get(key):
                            params[key] = stored_creds[key]

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

                # ── Cookie validity check: after the first goto, detect login redirect ──
                if action == "goto" and not cookie_check_done and result.status == StepStatus.passed:
                    cookie_check_done = True
                    try:
                        login_info = await is_likely_login_page(page)
                        if login_info["is_login"] and cookies:
                            # Cookies were provided but we landed on a login page → cookies likely expired
                            await self._broadcaster.emit(WsMessage(
                                event="cookie_invalid",
                                run_id=run.id,
                                step_index=i,
                                status="warning",
                                action=action,
                                params_summary=login_info["reason"],
                                screenshot_before=before_url,
                            ))
                            logger.warning(
                                "Cookies appear invalid for run=%s: %s",
                                run.id,
                                login_info["reason"],
                            )
                    except Exception:
                        logger.debug("cookie validity check failed", exc_info=True)

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
                after_path = self._storage.screenshot_path(run.id, i, suffix="_after")
                after_url: str | None = None
                try:
                    await self._storage.save_screenshot(page, after_path)
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
            try:
                await bm.close()
            except Exception:
                logger.warning("Browser close failed for run=%s", run.id)

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


def _safe_json(obj: dict) -> str:
    """JSON-encode a dict safely for embedding inside a JS template string."""
    import json
    return json.dumps(obj, ensure_ascii=False)


def _decrypt_stored_credentials(creds: dict | None) -> dict | None:
    """Return a copy of creds with password_encrypted decrypted to 'password'."""
    if not creds or not isinstance(creds, dict):
        return None
    out = dict(creds)
    enc = out.pop("password_encrypted", None)
    if enc:
        try:
            from app.core.security import decrypt_value
            out["password"] = decrypt_value(enc)
        except Exception:
            logger.warning("Failed to decrypt stored password; login will likely fail")
    return out


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
