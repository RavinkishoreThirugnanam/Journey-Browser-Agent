import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from core.config import STORAGE_DIR
from routers.test_case_router import list_test_cases
from schemas.test_script_schema import TestScriptGenerateRequest, TestScriptListResponse
from services.artifact_file_service import write_json_file, write_text_file, unique_filename
from services.journey_map_service import get_journey
from services.test_case_agent_service import build_source_evidence
from services.test_script_agent_service import generate_test_scripts

router = APIRouter()
TEST_SCRIPTS_FILE = STORAGE_DIR / "test_scripts.json"
GENERATED_DIR = STORAGE_DIR / "generated_files"


def _write(items):
    TEST_SCRIPTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TEST_SCRIPTS_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")


def _read():
    if not TEST_SCRIPTS_FILE.exists():
        return []
    raw = TEST_SCRIPTS_FILE.read_text(encoding="utf-8")
    return json.loads(raw) if raw.strip() else []

def _evidence_for_case(test_case: dict) -> list[dict]:
    stored = test_case.get("source_evidence")
    evidence = [item for item in stored if isinstance(item, dict)] if isinstance(stored, list) else []
    if evidence:
        return evidence
    journey_id = str(test_case.get("journey_id") or "")
    journey = get_journey(journey_id) if journey_id else None
    return build_source_evidence(journey) if journey else []


def _with_source_evidence(test_case: dict) -> dict:
    evidence = _evidence_for_case(test_case)
    if not evidence or test_case.get("source_evidence"):
        return test_case
    return {**test_case, "source_evidence": evidence}


def _safe_evidence_count(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


@router.post("/test-scripts/generate", response_model=TestScriptListResponse)
def generate(payload: TestScriptGenerateRequest):
    selected_ids = set(payload.test_case_ids)
    if not selected_ids:
        raise HTTPException(status_code=400, detail="Select at least one test case to generate scripts")

    test_cases = [_with_source_evidence(tc) for tc in list_test_cases()["items"] if tc["test_case_id"] in selected_ids]
    scripts = [item.model_dump() for item in generate_test_scripts(test_cases)]
    generated_at = datetime.now(timezone.utc).isoformat()
    for script in scripts:
        script["generated_at"] = generated_at
    for script in scripts:
        write_text_file(script["feature_filename"], script["feature_file"])
        write_text_file(script["javascript_filename"], script["javascript_file"])

    # Preserve scripts from other test cases so the UI can show historical artifacts
    # by selected story/test-case context instead of only the latest generation.
    existing_scripts = [script for script in _read() if script.get("test_case_id") not in selected_ids]
    _write(existing_scripts + scripts)
    return {"items": scripts, "count": len(scripts)}


@router.get("/test-scripts", response_model=TestScriptListResponse)
def list_test_scripts():
    test_cases = {str(item.get("test_case_id") or ""): item for item in list_test_cases()["items"]}
    items = []
    for stored_script in _read():
        script = dict(stored_script)
        test_case = test_cases.get(str(script.get("test_case_id") or ""))
        linked_count = len(_evidence_for_case(test_case)) if test_case else 0
        script["source_evidence_count"] = max(_safe_evidence_count(script.get("source_evidence_count")), linked_count)
        items.append(script)
    return {"items": items, "count": len(items)}


@router.get("/test-scripts/{script_id}/download/{artifact_format}")
def download_script_artifact(script_id: str, artifact_format: str):
    if artifact_format not in {"feature", "javascript"}:
        raise HTTPException(status_code=400, detail="Artifact format must be feature or javascript")
    script = next((item for item in _read() if item.get("script_id") == script_id), None)
    if not script:
        raise HTTPException(status_code=404, detail="Test script not found")
    key = "feature_filename" if artifact_format == "feature" else "javascript_filename"
    filename = script.get(key)
    path = GENERATED_DIR / filename if filename else None
    if not path or not path.exists():
        content_key = "feature_file" if artifact_format == "feature" else "javascript_file"
        filename = filename or f"{script_id}.{'feature' if artifact_format == 'feature' else 'spec.js'}"
        path = write_text_file(filename, script.get(content_key, ""))
    media_type = "text/plain; charset=utf-8"
    return FileResponse(path, filename=filename, media_type=media_type)


@router.get("/test-scripts/download")
def download_test_scripts():
    items = _read()
    filename = unique_filename("test_scripts", ".json")
    path = write_json_file(filename, items)
    return FileResponse(path, filename=filename, media_type="application/json")