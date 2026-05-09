"""Runs CRUD API."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, async_session
from app.models.test_case import TestCase
from app.models.run import Run, RunStatus
from app.models.run_step import RunStep, StepStatus
from app.models.step_diagnosis import StepDiagnosis
from app.engine.step_capturer import load_step_details

router = APIRouter(prefix="/runs", tags=["runs"])

logger = logging.getLogger(__name__)

# ── Schemas ──

from datetime import datetime, timezone

class RunOut(BaseModel):
    id: int
    test_case_id: int
    project_id: int | None = None
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    narrative: dict | None = None

    class Config:
        from_attributes = True


class RunStepOut(BaseModel):
    id: int
    run_id: int
    step_index: int
    action: str
    input_json: dict | None = None
    output_json: dict | None = None
    screenshot_path: str | None = None
    status: str
    duration_ms: int | None = None
    error: str | None = None

    class Config:
        from_attributes = True


class StepDetailsOut(BaseModel):
    console_logs: list[dict] = []
    network_requests: list[dict] = []
    dom_snippet: str | None = None
    target_bbox: dict | None = None


class StepDiagnosisOut(BaseModel):
    id: int
    run_id: int
    step_index: int
    payload_json: dict
    created_at: datetime | None = None

    class Config:
        from_attributes = True


# ── Endpoints ──

def _parse_narrative(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


@router.get("/{run_id}", response_model=RunOut)
async def get_run(run_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Run).options(joinedload(Run.test_case)).where(Run.id == run_id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Run not found")
    # Build response manually to include project_id from test_case
    return RunOut(
        id=run.id,
        test_case_id=run.test_case_id,
        project_id=run.test_case.project_id if run.test_case else None,
        status=run.status.value,
        started_at=run.started_at,
        finished_at=run.finished_at,
        narrative=_parse_narrative(run.narrative),
    )


@router.get("/{run_id}/steps", response_model=list[RunStepOut])
async def get_run_steps(run_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(RunStep).where(RunStep.run_id == run_id).order_by(RunStep.step_index)
    )
    return result.scalars().all()


@router.get("/{run_id}/steps/{step_index}/details", response_model=StepDetailsOut)
async def get_step_details(run_id: int, step_index: int):
    data = load_step_details(run_id, step_index)
    if data is None:
        # Gracefully return empty details for legacy runs or missing captures
        return StepDetailsOut()
    return StepDetailsOut(
        console_logs=data.console_logs,
        network_requests=data.network_requests,
        dom_snippet=data.dom_snippet,
        target_bbox=data.target_bbox,
    )


@router.get("/{run_id}/steps/{step_index}/diagnosis", response_model=StepDiagnosisOut)
async def get_step_diagnosis(run_id: int, step_index: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(StepDiagnosis)
        .where(StepDiagnosis.run_id == run_id, StepDiagnosis.step_index == step_index)
    )
    diagnosis = result.scalar_one_or_none()
    if not diagnosis:
        raise HTTPException(404, "Diagnosis not found")
    return diagnosis


@router.post("/{run_id}/steps/{step_index}/ai-diagnose", response_model=StepDiagnosisOut)
async def ai_diagnose(
    run_id: int,
    step_index: int,
    body: AiDiagnoseRequest,
    db: AsyncSession = Depends(get_db),
):
    """Run AI-powered diagnosis for a failed step."""
    # Verify the step exists and is failed
    step_result = await db.execute(
        select(RunStep)
        .where(RunStep.run_id == run_id, RunStep.step_index == step_index)
    )
    step = step_result.scalar_one_or_none()
    if not step:
        raise HTTPException(404, "Step not found")
    if step.status != StepStatus.failed:
        raise HTTPException(400, "AI diagnosis is only available for failed steps")

    try:
        from app.engine.ai_diagnosis import diagnose_with_ai
        diagnosis = await diagnose_with_ai(
            db=db,
            run_id=run_id,
            step_index=step_index,
            llm_config_id=body.llm_config_id,
        )
        await db.commit()
        return diagnosis
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.exception("AI diagnosis failed for run=%s step=%s", run_id, step_index)
        raise HTTPException(500, f"AI diagnosis failed: {exc}")


class AiDiagnoseRequest(BaseModel):
    llm_config_id: int | None = None


class RunCreate(BaseModel):
    test_case_id: int


async def _execute_run(test_case_id: int, run_id: int) -> None:
    """Background task: execute a run using the Runner engine."""
    from app.engine.runner import Runner
    from app.engine.ws_broadcaster import SocketIoBroadcaster
    from app.ws.socketio_server import sio
    from app.engine.models import WsMessage

    try:
        async with async_session() as db:
            # Load test case with project relationship
            result = await db.execute(
                select(TestCase)
                .options(selectinload(TestCase.project))
                .where(TestCase.id == test_case_id)
            )
            tc = result.scalar_one_or_none()
            if not tc:
                logger.error("Test case %s not found for run %s", test_case_id, run_id)
                return

            broadcaster = SocketIoBroadcaster(sio)
            runner = Runner(db=db, broadcaster=broadcaster)
            await runner.run(tc, run_id=run_id)
            await db.commit()

            # Generate narrative after run completes
            try:
                async with async_session() as narrative_db:
                    from app.llm.narrative import generate_run_narrative
                    await generate_run_narrative(narrative_db, run_id)
                    await narrative_db.commit()
            except Exception:
                logger.exception("Narrative generation failed for run_id=%s", run_id)
    except Exception:
        logger.exception("Run execution failed for run_id=%s", run_id)
        # Mark run as failed so the UI doesn't hang on "pending"
        try:
            async with async_session() as db:
                result = await db.execute(select(Run).where(Run.id == run_id))
                run = result.scalar_one_or_none()
                if run:
                    run.status = RunStatus.failed
                    run.finished_at = datetime.now(timezone.utc)
                    await db.commit()
                # Notify any connected clients
                broadcaster = SocketIoBroadcaster(sio)
                await broadcaster.emit(WsMessage(
                    event="run_end",
                    run_id=run_id,
                    step_index=None,
                    status=RunStatus.failed.value,
                ))
        except Exception:
            logger.exception("Failed to mark run %s as failed after error", run_id)


@router.post("", response_model=RunOut, status_code=201)
async def create_run(body: RunCreate, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """Create a new run for a test case and start execution in background."""
    # Verify test case exists
    result = await db.execute(select(TestCase).where(TestCase.id == body.test_case_id))
    tc = result.scalar_one_or_none()
    if not tc:
        raise HTTPException(404, "Test case not found")
    run = Run(test_case_id=body.test_case_id, status=RunStatus.pending)
    db.add(run)
    await db.flush()
    await db.refresh(run)
    await db.commit()

    # Start the runner in the background using FastAPI BackgroundTasks
    background_tasks.add_task(_execute_run, body.test_case_id, run.id)

    return run


@router.post("/{run_id}/narrative", response_model=RunOut)
async def generate_narrative(run_id: int, db: AsyncSession = Depends(get_db)):
    """Manually trigger narrative generation for a run."""
    result = await db.execute(select(Run).options(joinedload(Run.test_case)).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Run not found")

    if run.status not in (RunStatus.passed, RunStatus.failed):
        raise HTTPException(400, "Narrative can only be generated for completed runs")

    try:
        from app.llm.narrative import generate_run_narrative
        await generate_run_narrative(db, run_id)
        await db.commit()
    except Exception as exc:
        logger.exception("Manual narrative generation failed for run=%s", run_id)
        raise HTTPException(500, f"Narrative generation failed: {exc}")

    return RunOut(
        id=run.id,
        test_case_id=run.test_case_id,
        project_id=run.test_case.project_id if run.test_case else None,
        status=run.status.value,
        started_at=run.started_at,
        finished_at=run.finished_at,
        narrative=_parse_narrative(run.narrative),
    )


# ── Export ──

from fastapi.responses import FileResponse
from app.reports.exporter import export_run_report
from app.reports.token import sign_export_token, verify_export_token


class ExportRequest(BaseModel):
    format: str = "html"  # html | pdf


class ExportOut(BaseModel):
    download_url: str
    filename: str
    expires_at: datetime


@router.post("/{run_id}/export", response_model=ExportOut)
async def export_run(
    run_id: int,
    body: ExportRequest,
    db: AsyncSession = Depends(get_db),
):
    """Export a run report as self-contained HTML or PDF."""
    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Run not found")

    fmt = body.format.lower()
    if fmt not in ("html", "pdf"):
        raise HTTPException(400, "format must be 'html' or 'pdf'")

    try:
        export_result = await export_run_report(db, run_id, fmt=fmt)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:
        logger.exception("Export failed for run=%s", run_id)
        raise HTTPException(500, f"Export failed: {exc}")

    token = sign_export_token(run_id, export_result.filename)
    download_url = f"/api/v1/runs/{run_id}/export/download?filename={export_result.filename}&token={token}"

    return ExportOut(
        download_url=download_url,
        filename=export_result.filename,
        expires_at=datetime.now(timezone.utc).replace(hour=datetime.now(timezone.utc).hour + 24),
    )


@router.get("/{run_id}/export/download")
async def download_export(run_id: int, filename: str, token: str):
    """Download an exported report with signed token."""
    if not verify_export_token(token, run_id, filename):
        raise HTTPException(403, "Invalid or expired download token")

    filepath = Path("storage/exports") / filename
    if not filepath.exists():
        raise HTTPException(404, "Export file not found")

    media_type = "application/pdf" if filename.endswith(".pdf") else "text/html; charset=utf-8"
    return FileResponse(
        path=str(filepath),
        media_type=media_type,
        filename=filename,
    )
