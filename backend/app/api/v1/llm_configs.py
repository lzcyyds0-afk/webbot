"""LLM Configs CRUD API (extends existing llm/test endpoint)."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.llm_config import LLMConfig

router = APIRouter(prefix="/llm/configs", tags=["llm-configs"])


# ── Schemas ──

class LLMConfigCreate(BaseModel):
    name: str
    provider: str
    model: str
    api_key: str
    base_url: str | None = None
    params_json: dict | None = None
    is_default: bool = False


class LLMConfigUpdate(BaseModel):
    name: str | None = None
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    params_json: dict | None = None
    is_default: bool | None = None


class LLMConfigOut(BaseModel):
    id: int
    name: str
    provider: str
    model: str
    base_url: str | None = None
    params_json: dict | None = None
    is_default: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


# ── Endpoints ──

@router.get("", response_model=list[LLMConfigOut])
async def list_configs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LLMConfig).order_by(LLMConfig.id))
    return result.scalars().all()


@router.post("", response_model=LLMConfigOut, status_code=201)
async def create_config(body: LLMConfigCreate, db: AsyncSession = Depends(get_db)):
    # If setting as default, clear other defaults
    if body.is_default:
        result = await db.execute(select(LLMConfig).where(LLMConfig.is_default == True))
        for old in result.scalars().all():
            old.is_default = False

    cfg = LLMConfig(
        name=body.name,
        provider=body.provider,
        model=body.model,
        base_url=body.base_url,
        params_json=body.params_json,
        is_default=body.is_default,
    )
    cfg.set_plain_key(body.api_key)
    db.add(cfg)
    await db.flush()
    await db.refresh(cfg)
    return cfg


@router.get("/{config_id}", response_model=LLMConfigOut)
async def get_config(config_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LLMConfig).where(LLMConfig.id == config_id))
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(404, "LLMConfig not found")
    return cfg


@router.put("/{config_id}", response_model=LLMConfigOut)
async def update_config(config_id: int, body: LLMConfigUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LLMConfig).where(LLMConfig.id == config_id))
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(404, "LLMConfig not found")

    if body.is_default is True:
        old_result = await db.execute(select(LLMConfig).where(LLMConfig.is_default == True))
        for old in old_result.scalars().all():
            old.is_default = False

    if body.name is not None:
        cfg.name = body.name
    if body.provider is not None:
        cfg.provider = body.provider
    if body.model is not None:
        cfg.model = body.model
    if body.api_key is not None:
        cfg.set_plain_key(body.api_key)
    if body.base_url is not None:
        cfg.base_url = body.base_url
    if body.params_json is not None:
        cfg.params_json = body.params_json
    if body.is_default is not None:
        cfg.is_default = body.is_default

    await db.flush()
    await db.refresh(cfg)
    return cfg


@router.delete("/{config_id}", status_code=204)
async def delete_config(config_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LLMConfig).where(LLMConfig.id == config_id))
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(404, "LLMConfig not found")
    await db.delete(cfg)
    await db.flush()