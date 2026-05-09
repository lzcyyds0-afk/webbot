"""Projects CRUD API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.project import Project
from app.models.test_case import TestCase

router = APIRouter(prefix="/projects", tags=["projects"])


# ── Schemas ──

class ProjectCreate(BaseModel):
    name: str
    base_url: HttpUrl


class ProjectUpdate(BaseModel):
    name: str | None = None
    base_url: HttpUrl | None = None


from datetime import datetime

class ProjectOut(BaseModel):
    id: int
    name: str
    base_url: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


# ── Endpoints ──

@router.get("", response_model=list[ProjectOut])
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).order_by(Project.id))
    return result.scalars().all()


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectCreate, db: AsyncSession = Depends(get_db)):
    proj = Project(name=body.name, base_url=str(body.base_url))
    db.add(proj)
    await db.flush()
    await db.refresh(proj)
    return proj


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    proj = result.scalar_one_or_none()
    if not proj:
        raise HTTPException(404, "Project not found")
    return proj


@router.put("/{project_id}", response_model=ProjectOut)
async def update_project(project_id: int, body: ProjectUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    proj = result.scalar_one_or_none()
    if not proj:
        raise HTTPException(404, "Project not found")
    if body.name is not None:
        proj.name = body.name
    if body.base_url is not None:
        proj.base_url = str(body.base_url)
    await db.flush()
    await db.refresh(proj)
    return proj


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    proj = result.scalar_one_or_none()
    if not proj:
        raise HTTPException(404, "Project not found")
    await db.delete(proj)
    await db.flush()
