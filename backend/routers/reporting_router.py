from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.config import STORAGE_DIR
from core.step5_reporting_module import run_reporting_pipeline
from schemas.configuration_schema import Configuration
from routers.configuration_router import _read as read_configuration

router = APIRouter()


class ReportingRunRequest(BaseModel):
    report_path: str = Field(..., description='Path to a Cucumber JSON file or directory of JSON reports')
    output_dir: str | None = Field(default=None, description='Optional output directory for saved Jira payloads')
    push_to_jira: bool = Field(default=False, description='Whether to create Jira bugs for failed scenarios')


@router.post('/reporting/run')
async def run_reporting(payload: ReportingRunRequest) -> dict[str, Any]:
    config_data = read_configuration()
    jira_config = Configuration(**config_data).jira
    output_dir = payload.output_dir or str(STORAGE_DIR / 'generated_files' / 'reporting')
    try:
        return await run_reporting_pipeline(payload.report_path, output_dir, jira_config=jira_config, push_to_jira=payload.push_to_jira)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
