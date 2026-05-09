"""Test Cases CRUD API."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.project import Project
from app.models.test_case import TestCase

router = APIRouter(prefix="/projects/{project_id}/test-cases", tags=["test-cases"])


# ── Schemas ──

class TestCaseCreate(BaseModel):
    name: str


class TestCaseUpdate(BaseModel):
    name: str | None = None
    steps_json: list[dict] | None = None
    cookies_json: list[dict] | None = None


class TestCaseOut(BaseModel):
    id: int
    project_id: int
    name: str
    steps_json: list[dict]
    cookies_json: list[dict] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


# ── Helpers ──

async def _get_project(project_id: int, db: AsyncSession) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    proj = result.scalar_one_or_none()
    if not proj:
        raise HTTPException(404, "Project not found")
    return proj


# ── Endpoints ──

@router.get("", response_model=list[TestCaseOut])
async def list_test_cases(project_id: int, db: AsyncSession = Depends(get_db)):
    await _get_project(project_id, db)
    result = await db.execute(
        select(TestCase).where(TestCase.project_id == project_id).order_by(TestCase.id)
    )
    return result.scalars().all()


@router.post("", response_model=TestCaseOut, status_code=201)
async def create_test_case(project_id: int, body: TestCaseCreate, db: AsyncSession = Depends(get_db)):
    await _get_project(project_id, db)
    tc = TestCase(project_id=project_id, name=body.name, steps_json=[])
    db.add(tc)
    await db.flush()
    await db.refresh(tc)
    return tc


@router.get("/{case_id}", response_model=TestCaseOut)
async def get_test_case(project_id: int, case_id: int, db: AsyncSession = Depends(get_db)):
    await _get_project(project_id, db)
    result = await db.execute(
        select(TestCase).where(TestCase.id == case_id, TestCase.project_id == project_id)
    )
    tc = result.scalar_one_or_none()
    if not tc:
        raise HTTPException(404, "Test case not found")
    return tc


@router.put("/{case_id}", response_model=TestCaseOut)
async def update_test_case(
    project_id: int, case_id: int, body: TestCaseUpdate, db: AsyncSession = Depends(get_db)
):
    await _get_project(project_id, db)
    result = await db.execute(
        select(TestCase).where(TestCase.id == case_id, TestCase.project_id == project_id)
    )
    tc = result.scalar_one_or_none()
    if not tc:
        raise HTTPException(404, "Test case not found")
    if body.name is not None:
        tc.name = body.name
    if body.steps_json is not None:
        tc.steps_json = body.steps_json
    if body.cookies_json is not None:
        tc.cookies_json = body.cookies_json
    await db.flush()
    await db.refresh(tc)
    return tc


@router.delete("/{case_id}", status_code=204)
async def delete_test_case(project_id: int, case_id: int, db: AsyncSession = Depends(get_db)):
    await _get_project(project_id, db)
    result = await db.execute(
        select(TestCase).where(TestCase.id == case_id, TestCase.project_id == project_id)
    )
    tc = result.scalar_one_or_none()
    if not tc:
        raise HTTPException(404, "Test case not found")
    await db.delete(tc)
    await db.flush()