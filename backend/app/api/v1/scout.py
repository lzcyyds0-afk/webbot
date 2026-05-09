from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.llm.scout import (
    ScoutRequest,
    ScoutResponse,
    ScoutError,
    scout_page,
)

router = APIRouter(prefix="/scout", tags=["scout"])


@router.post("", response_model=ScoutResponse)
async def scout(
    req: ScoutRequest,
    db: AsyncSession = Depends(get_db),
):
    """Explore a web page and generate test path suggestions.

    Workflow:
    1. Open URL with Playwright, screenshot + extract interactive elements
    2. Send screenshot + summary + optional goal to vision LLM
    3. Parse & validate JSON output (retry once on failure)
    4. Return suggested test paths with risk levels
    """
    try:
        result = await scout_page(req, db)
        return result
    except ScoutError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Scout failed: {exc}")
