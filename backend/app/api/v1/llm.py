from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.llm_config import LLMConfig
from app.llm import get_provider, Message

router = APIRouter(prefix="/llm", tags=["llm"])


class LLMTestRequest(BaseModel):
    config_id: int
    prompt: str


class LLMTestResponse(BaseModel):
    content: str
    usage: dict
    model: str
    success: bool
    error: str | None = None


@router.post("/test", response_model=LLMTestResponse)
async def test_llm(
    req: LLMTestRequest,
    db: AsyncSession = Depends(get_db),
):
    """Test LLM connectivity: send a prompt and return the model response."""
    # 1. Load config from DB
    result = await db.execute(
        select(LLMConfig).where(LLMConfig.id == req.config_id)
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=404, detail=f"LLMConfig {req.config_id} not found")

    # 2. Instantiate provider
    try:
        provider = get_provider(config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # 3. Call chat
    try:
        chat_result = await provider.chat(
            messages=[Message(role="user", content=req.prompt)],
            temperature=0.7,
            max_tokens=256,
        )
        return LLMTestResponse(
            content=chat_result.content,
            usage=chat_result.usage.model_dump(),
            model=chat_result.model,
            success=True,
        )
    except Exception as exc:
        return LLMTestResponse(
            content="",
            usage={},
            model=config.model,
            success=False,
            error=str(exc),
        )
