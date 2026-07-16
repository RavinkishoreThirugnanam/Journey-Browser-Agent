import json

from fastapi import APIRouter
from fastapi.responses import FileResponse

from core.config import STORAGE_DIR
from routers.test_case_router import list_test_cases
from schemas.test_script_schema import TestScriptGenerateRequest, TestScriptListResponse
from services.artifact_file_service import write_json_file, unique_filename
from services.test_script_agent_service import generate_test_scripts

router = APIRouter()
TEST_SCRIPTS_FILE = STORAGE_DIR / "test_scripts.json"


def _write(items):
    TEST_SCRIPTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TEST_SCRIPTS_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")


def _read():
    if not TEST_SCRIPTS_FILE.exists():
        return []
    raw = TEST_SCRIPTS_FILE.read_text(encoding="utf-8")
    return json.loads(raw) if raw.strip() else []


@router.post("/test-scripts/generate", response_model=TestScriptListResponse)
def generate(payload: TestScriptGenerateRequest):
    test_cases = [tc for tc in list_test_cases()["items"] if tc["test_case_id"] in payload.test_case_ids]
    scripts = [item.model_dump() for item in generate_test_scripts(test_cases)]
    _write(scripts)
    return {"items": scripts, "count": len(scripts)}


@router.get("/test-scripts", response_model=TestScriptListResponse)
def list_test_scripts():
    items = _read()
    return {"items": items, "count": len(items)}


@router.get("/test-scripts/download")
def download_test_scripts():
    items = _read()
    filename = unique_filename("test_scripts", ".json")
    path = write_json_file(filename, items)
    return FileResponse(path, filename=filename, media_type="application/json")
