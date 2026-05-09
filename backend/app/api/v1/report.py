"""Project-level aggregated report API."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.project import Project
from app.models.run import Run, RunStatus
from app.models.run_step import RunStep, StepStatus
from app.models.step_diagnosis import StepDiagnosis
from app.models.test_case import TestCase

router = APIRouter(prefix="/projects", tags=["report"])


# ── Schemas ──

class TrendPoint(BaseModel):
    date: str
    total: int
    passed: int
    failed: int
    pass_rate: float


class DurationByAction(BaseModel):
    action: str
    count: int
    p50: int
    p95: int


class FailedStepTop(BaseModel):
    action: str
    selector: str
    failure_count: int
    last_failed_at: str | None
    last_run_id: int
    last_run_step_index: int


class ActionSuccessRate(BaseModel):
    action: str
    total: int
    passed: int
    failed: int
    rate: float


class AiConfidence(BaseModel):
    bins: list[float]
    counts: list[int]
    avg: float | None


class Kpi(BaseModel):
    total_runs: int
    pass_rate: float
    avg_duration_ms: int | None
    failed_cases: int


class ProjectReportOut(BaseModel):
    kpi: Kpi
    trend: list[TrendPoint]
    duration_by_action: list[DurationByAction]
    failed_steps_top: list[FailedStepTop]
    action_success_rate: list[ActionSuccessRate]
    ai_confidence: AiConfidence


# ── Helpers ──

def _parse_date_range(
    from_date: date | None,
    to_date: date | None,
) -> tuple[datetime, datetime]:
    if from_date is None:
        from_date = date.today() - timedelta(days=30)
    if to_date is None:
        to_date = date.today()
    return (
        datetime.combine(from_date, time.min),
        datetime.combine(to_date, time.max),
    )


def _percentile(sorted_vals: list[int], p: float) -> int:
    if not sorted_vals:
        return 0
    n = len(sorted_vals)
    idx = int(n * p)
    return sorted_vals[min(idx, n - 1)]


# ── Endpoint ──

@router.get("/{project_id}/report", response_model=ProjectReportOut)
async def get_project_report(
    project_id: int,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
    db: AsyncSession = Depends(get_db),
) -> ProjectReportOut:
    # Verify project exists
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    if proj_result.scalar_one_or_none() is None:
        raise HTTPException(404, "Project not found")

    from_dt, to_dt = _parse_date_range(from_date, to_date)

    # ── 1. Fetch runs in range ──
    runs_stmt = (
        select(Run.status, Run.started_at, Run.finished_at, Run.test_case_id)
        .join(TestCase, Run.test_case_id == TestCase.id)
        .where(
            TestCase.project_id == project_id,
            Run.started_at >= from_dt,
            Run.started_at <= to_dt,
        )
    )
    runs_rows = (await db.execute(runs_stmt)).all()
    run_ids = [r.id for r in (await db.execute(
        select(Run.id)
        .join(TestCase, Run.test_case_id == TestCase.id)
        .where(
            TestCase.project_id == project_id,
            Run.started_at >= from_dt,
            Run.started_at <= to_dt,
        )
    )).all()]

    total_runs = len(runs_rows)
    passed_count = sum(1 for r in runs_rows if r.status == RunStatus.passed)
    pass_rate = round(passed_count / total_runs, 4) if total_runs > 0 else 0.0

    durations: list[int] = []
    for r in runs_rows:
        if r.started_at and r.finished_at:
            durations.append(int((r.finished_at - r.started_at).total_seconds() * 1000))
    avg_duration_ms = int(sum(durations) / len(durations)) if durations else None

    failed_cases = len({r.test_case_id for r in runs_rows if r.status == RunStatus.failed})

    kpi = Kpi(
        total_runs=total_runs,
        pass_rate=pass_rate,
        avg_duration_ms=avg_duration_ms,
        failed_cases=failed_cases,
    )

    # ── 2. Trend (daily) ──
    trend: list[TrendPoint] = []
    if run_ids:
        trend_stmt = (
            select(
                func.date(Run.started_at).label("date"),
                func.count(Run.id).label("total"),
                func.sum(case((Run.status == RunStatus.passed, 1), else_=0)).label("passed"),
                func.sum(case((Run.status == RunStatus.failed, 1), else_=0)).label("failed"),
            )
            .where(Run.id.in_(run_ids))
            .group_by(func.date(Run.started_at))
            .order_by(func.date(Run.started_at))
        )
        trend_rows = (await db.execute(trend_stmt)).all()
        for row in trend_rows:
            t_total = row.total
            t_passed = row.passed or 0
            t_failed = row.failed or 0
            trend.append(TrendPoint(
                date=str(row.date),
                total=t_total,
                passed=t_passed,
                failed=t_failed,
                pass_rate=round(t_passed / t_total, 4) if t_total > 0 else 0.0,
            ))

    # ── 3. Duration by action (P50 / P95) ──
    duration_by_action: list[DurationByAction] = []
    if run_ids:
        dur_stmt = (
            select(RunStep.action, RunStep.duration_ms)
            .where(RunStep.run_id.in_(run_ids))
            .where(RunStep.duration_ms.is_not(None))
        )
        dur_rows = (await db.execute(dur_stmt)).all()
        action_durations: dict[str, list[int]] = defaultdict(list)
        for action, duration in dur_rows:
            action_durations[action].append(duration)
        for action, vals in action_durations.items():
            vals.sort()
            n = len(vals)
            p50 = vals[n // 2] if n % 2 == 1 else (vals[n // 2 - 1] + vals[n // 2]) // 2
            p95 = _percentile(vals, 0.95)
            duration_by_action.append(DurationByAction(
                action=action, count=n, p50=p50, p95=p95,
            ))
        duration_by_action.sort(key=lambda x: x.count, reverse=True)

    # ── 4. Failed steps TOP N ──
    failed_steps_top: list[FailedStepTop] = []
    if run_ids:
        fail_stmt = (
            select(RunStep.action, RunStep.input_json, RunStep.run_id, RunStep.step_index, Run.started_at)
            .join(Run, RunStep.run_id == Run.id)
            .where(RunStep.run_id.in_(run_ids))
            .where(RunStep.status == StepStatus.failed)
            .order_by(Run.started_at.desc())
        )
        fail_rows = (await db.execute(fail_stmt)).all()
        fail_groups: dict[tuple[str, str], dict] = defaultdict(
            lambda: {"count": 0, "last_at": None, "last_run_id": None, "last_step": None}
        )
        for action, input_json, rid, step_idx, started_at in fail_rows:
            selector = ""
            if input_json:
                selector = (
                    input_json.get("selector")
                    or input_json.get("from_selector")
                    or input_json.get("to_selector")
                    or ""
                )
            key = (action, selector)
            g = fail_groups[key]
            g["count"] += 1
            if g["last_at"] is None or started_at > g["last_at"]:
                g["last_at"] = started_at
                g["last_run_id"] = rid
                g["last_step"] = step_idx

        for (action, selector), g in sorted(
            fail_groups.items(), key=lambda x: x[1]["count"], reverse=True
        )[:10]:
            failed_steps_top.append(FailedStepTop(
                action=action,
                selector=selector,
                failure_count=g["count"],
                last_failed_at=g["last_at"].isoformat() if g["last_at"] else None,
                last_run_id=g["last_run_id"] or 0,
                last_run_step_index=g["last_step"] or 0,
            ))

    # ── 5. Action success rate ──
    action_success_rate: list[ActionSuccessRate] = []
    if run_ids:
        act_stmt = (
            select(
                RunStep.action,
                func.count(RunStep.id).label("total"),
                func.sum(case((RunStep.status == StepStatus.passed, 1), else_=0)).label("passed"),
                func.sum(case((RunStep.status == StepStatus.failed, 1), else_=0)).label("failed"),
            )
            .where(RunStep.run_id.in_(run_ids))
            .group_by(RunStep.action)
        )
        act_rows = (await db.execute(act_stmt)).all()
        for action, total, passed, failed in act_rows:
            rate = (passed or 0) / total if total > 0 else 0.0
            action_success_rate.append(ActionSuccessRate(
                action=action,
                total=total,
                passed=passed or 0,
                failed=failed or 0,
                rate=round(rate, 4),
            ))
        action_success_rate.sort(key=lambda x: x.total, reverse=True)

    # ── 6. AI confidence distribution ──
    bins = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    counts = [0] * (len(bins) - 1)
    confidences: list[float] = []
    if run_ids:
        diag_stmt = (
            select(StepDiagnosis.payload_json)
            .where(StepDiagnosis.run_id.in_(run_ids))
        )
        diag_rows = (await db.execute(diag_stmt)).all()
        for payload, in diag_rows:
            if isinstance(payload, dict):
                ai_diag = payload.get("ai_diagnosis")
                if isinstance(ai_diag, dict):
                    conf = ai_diag.get("confidence")
                    if isinstance(conf, (int, float)) and 0.0 <= conf <= 1.0:
                        confidences.append(conf)
        for c in confidences:
            placed = False
            for i in range(len(bins) - 1):
                if bins[i] <= c < bins[i + 1]:
                    counts[i] += 1
                    placed = True
                    break
            if not placed and c == 1.0:
                counts[-1] += 1

    ai_confidence = AiConfidence(
        bins=bins,
        counts=counts,
        avg=round(sum(confidences) / len(confidences), 4) if confidences else None,
    )

    return ProjectReportOut(
        kpi=kpi,
        trend=trend,
        duration_by_action=duration_by_action,
        failed_steps_top=failed_steps_top,
        action_success_rate=action_success_rate,
        ai_confidence=ai_confidence,
    )
