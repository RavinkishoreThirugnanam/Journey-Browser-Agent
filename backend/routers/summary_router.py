from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.step6_summary import run_summary_pipeline

router = APIRouter()


class SummaryRunRequest(BaseModel):
    output_dir: str | None = Field(default=None, description='Optional directory containing pipeline artifacts and where the summary will be written')


@router.post('/summary/run')
async def run_summary(payload: SummaryRunRequest | None = None) -> dict[str, Any]:
    try:
        return await run_summary_pipeline(payload.output_dir if payload else None)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
