from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.database import get_db
from app.llm.generate import (
    GenerateRequest,
    GenerateResponse,
    GenerateError,
    generate_steps,
    RefineRequest as _RefineRequest,
    RefineResponse as _RefineResponse,
    refine_steps,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/cases", tags=["cases"])


# ── Refine schemas (mirror internal models for API docs) ──

class RefineRequest(BaseModel):
    steps: list[dict]
    user_feedback: str
    llm_config_id: int


class RefineResponse(BaseModel):
    steps: list[dict]
    raw_llm_output: str | None = None


# ── Endpoints ──

@router.post("/generate", response_model=GenerateResponse)
async def generate_test_case(
    req: GenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Generate test steps from natural language goal.

    Workflow:
    1. Open URL with Playwright, screenshot + extract interactive elements
    2. Load few-shot examples from prompts/examples/ and optional reference case
    3. Send screenshot + summary + goal + style reference to vision LLM
    4. Parse & validate DSL JSON output (auto-repair on failure)
    5. Return steps for user to review/edit in the Monaco editor
    """
    try:
        result = await generate_steps(req, db)
        return result
    except GenerateError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Generation failed: {exc}")


@router.post("/refine", response_model=RefineResponse)
async def refine_test_case(
    req: RefineRequest,
    db: AsyncSession = Depends(get_db),
):
    """Refine existing steps based on user feedback.

    Example feedback:
    - "第 3 步之前加一个等待"
    - "把第 2 步的 selector 改成 #submit-btn"
    - "删除最后一步截图"
    """
    try:
        internal_req = _RefineRequest(
            steps=req.steps,
            user_feedback=req.user_feedback,
            llm_config_id=req.llm_config_id,
        )
        result = await refine_steps(internal_req, db)
        return RefineResponse(
            steps=result.steps,
            raw_llm_output=result.raw_llm_output,
        )
    except GenerateError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Refinement failed: {exc}")
