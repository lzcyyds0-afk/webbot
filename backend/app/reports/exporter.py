"""Run report export: HTML (self-contained) and PDF."""
from __future__ import annotations

import base64
import logging
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.storage import Storage
from app.engine.step_capturer import load_step_details
from app.models.project import Project
from app.models.run import Run, RunStatus
from app.models.run_step import RunStep, StepStatus
from app.models.step_diagnosis import StepDiagnosis
from app.models.test_case import TestCase
from app.reports.sanitizer import (
    sanitize_input_output,
    sanitize_console_logs,
    sanitize_network_requests,
    sanitize_step_error,
)

logger = logging.getLogger(__name__)

_EXPORTS_DIR = Path("storage/exports")
_TEMPLATES_DIR = Path(__file__).parent / "templates"

_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


class StepView(BaseModel):
    step_index: int
    action: str
    params_text: str
    status: str
    status_label: str
    duration: str
    error: str | None
    screenshot_before: str | None  # data URI or None
    screenshot_after: str | None


class FailureView(BaseModel):
    step_index: int
    action: str
    error: str
    diagnosis: str | None


class ExportResult(BaseModel):
    filepath: Path
    filename: str
    content_type: str


def _img_to_data_uri(path: Path) -> str | None:
    if not path.exists():
        return None
    mime, _ = mimetypes.guess_type(str(path))
    mime = mime or "image/png"
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode()
    return f"data:{mime};base64,{b64}"


def _format_duration(ms: int | None) -> str:
    if ms is None:
        return "—"
    if ms < 1000:
        return f"{ms}ms"
    return f"{ms / 1000:.1f}s"


def _format_datetime(dt: datetime | None) -> str:
    if not dt:
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _params_text(step: RunStep) -> str:
    data = sanitize_input_output(step.input_json) or {}
    parts = []
    for k, v in data.items():
        if k == "action":
            continue
        s = str(v)
        if len(s) > 80:
            s = s[:77] + "..."
        parts.append(f"{k}={s}")
    return ", ".join(parts) if parts else "—"


async def _load_diagnoses(db: AsyncSession, run_id: int) -> dict[int, StepDiagnosis]:
    result = await db.execute(
        select(StepDiagnosis).where(StepDiagnosis.run_id == run_id)
    )
    return {d.step_index: d for d in result.scalars().all()}


async def export_run_report(
    db: AsyncSession,
    run_id: int,
    *,
    fmt: str = "html",
) -> ExportResult:
    """Generate a self-contained HTML or PDF report for a run."""
    # Load run with related data
    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise ValueError(f"Run {run_id} not found")

    steps_result = await db.execute(
        select(RunStep).where(RunStep.run_id == run_id).order_by(RunStep.step_index)
    )
    steps = steps_result.scalars().all()

    tc_result = await db.execute(select(TestCase).where(TestCase.id == run.test_case_id))
    tc = tc_result.scalar_one_or_none()

    project = None
    if tc:
        proj_result = await db.execute(select(Project).where(Project.id == tc.project_id))
        project = proj_result.scalar_one_or_none()

    diagnoses = await _load_diagnoses(db, run_id)

    # Build step views
    storage = Storage()
    step_views: list[StepView] = []
    failures: list[FailureView] = []
    all_console_logs: list[dict] = []

    for s in steps:
        before_path = storage.screenshot_path(run_id, s.step_index)
        after_path = storage.screenshot_path(run_id, s.step_index, suffix="_after")
        before_uri = _img_to_data_uri(before_path)
        after_uri = _img_to_data_uri(after_path)

        error_clean = sanitize_step_error(s.error)
        step_views.append(
            StepView(
                step_index=s.step_index,
                action=s.action,
                params_text=_params_text(s),
                status=s.status.value,
                status_label="通过" if s.status == StepStatus.passed else "失败" if s.status == StepStatus.failed else s.status.value,
                duration=_format_duration(s.duration_ms),
                error=error_clean,
                screenshot_before=before_uri,
                screenshot_after=after_uri,
            )
        )

        if s.status == StepStatus.failed:
            diag = diagnoses.get(s.step_index)
            diag_text = None
            if diag and diag.payload_json:
                ai_diag = diag.payload_json.get("ai_diagnosis")
                if ai_diag:
                    diag_text = ai_diag.get("root_cause") or ai_diag.get("explanation")
                if not diag_text:
                    diag_text = diag.payload_json.get("summary", {}).get("error_text")
            failures.append(
                FailureView(
                    step_index=s.step_index,
                    action=s.action,
                    error=error_clean or "未知错误",
                    diagnosis=diag_text,
                )
            )

        # Load step details for console logs
        try:
            details = load_step_details(run_id, s.step_index)
            if details:
                logs = sanitize_console_logs(details.console_logs)
                for log in logs:
                    level = log.get("type", "info")
                    if level in ("error", "warning", "warn"):
                        all_console_logs.append({"level": level, "text": log.get("text", "")})
        except Exception:
            pass

    total = len(steps)
    passed = sum(1 for s in steps if s.status == StepStatus.passed)
    failed = sum(1 for s in steps if s.status == StepStatus.failed)
    pass_rate = f"{passed}/{total} ({round(passed/total*100)}%)" if total else "—"

    duration = "—"
    if run.started_at and run.finished_at:
        secs = (run.finished_at - run.started_at).total_seconds()
        if secs < 60:
            duration = f"{secs:.1f}s"
        else:
            duration = f"{int(secs//60)}m {int(secs%60)}s"

    narrative = None
    if run.narrative:
        try:
            import json
            narrative = json.loads(run.narrative)
        except Exception:
            pass

    # Render HTML
    template = _jinja_env.get_template("run_report.html")
    html_content = template.render(
        title=f"运行报告 #{run_id}",
        project_name=project.name if project else "—",
        case_name=tc.name if tc else "—",
        status_label="通过" if run.status == RunStatus.passed else "失败" if run.status == RunStatus.failed else run.status.value,
        border_color="#52c41a" if run.status == RunStatus.passed else "#ff4d4f" if run.status == RunStatus.failed else "#1677ff",
        run_id=run_id,
        started_at=_format_datetime(run.started_at),
        duration=duration,
        total_steps=total,
        passed_steps=passed,
        failed_steps=failed,
        pass_rate=pass_rate,
        narrative=narrative,
        steps=step_views,
        failures=failures,
        console_logs=all_console_logs[:50],  # cap at 50
    )

    _EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if fmt == "pdf":
        from app.engine.browser import BrowserManager

        html_path = _EXPORTS_DIR / f"run_{run_id}_{ts}.html"
        html_path.write_text(html_content, encoding="utf-8")

        pdf_path = _EXPORTS_DIR / f"run_{run_id}_{ts}.pdf"
        bm = BrowserManager(headless=True)
        try:
            await bm.start()
            page = await bm.browser.new_page()
            await page.goto(f"file://{html_path.resolve()}", wait_until="networkidle")
            await page.pdf(
                path=str(pdf_path),
                format="A4",
                landscape=True,
                print_background=True,
                display_header_footer=True,
                header_template=f"""
                    <div style="font-size:9px; color:#999; width:100%; padding:0 40px; display:flex; justify-content:space-between;">
                        <span>WebBot 运行报告 #{run_id}</span>
                        <span>{_format_datetime(run.started_at)}</span>
                    </div>
                """,
                footer_template=f"""
                    <div style="font-size:9px; color:#999; width:100%; padding:0 40px; display:flex; justify-content:space-between;">
                        <span>{tc.name if tc else ""}</span>
                        <span class="pageNumber"></span> / <span class="totalPages"></span>
                    </div>
                """,
                margin={"top": "60px", "bottom": "60px", "left": "30px", "right": "30px"},
            )
            await page.close()
        finally:
            try:
                await bm.close()
            except Exception:
                pass

        # Clean up intermediate HTML
        try:
            html_path.unlink()
        except Exception:
            pass

        return ExportResult(
            filepath=pdf_path,
            filename=pdf_path.name,
            content_type="application/pdf",
        )

    # HTML export
    html_path = _EXPORTS_DIR / f"run_{run_id}_{ts}.html"
    html_path.write_text(html_content, encoding="utf-8")
    return ExportResult(
        filepath=html_path,
        filename=html_path.name,
        content_type="text/html; charset=utf-8",
    )
