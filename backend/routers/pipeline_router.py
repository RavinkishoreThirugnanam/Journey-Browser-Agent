from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.step0_main import run_all

router = APIRouter()


class PipelineRunRequest(BaseModel):
    application_url: str | None = Field(default=None, description='Optional application URL override for the run')


@router.post('/pipeline/run-all')
async def run_pipeline(payload: PipelineRunRequest | None = None) -> dict[str, Any]:
    application_url = payload.application_url if payload else None
    try:
        return await run_all(application_url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
