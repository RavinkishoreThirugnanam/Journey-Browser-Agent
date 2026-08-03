import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from core.config import STORAGE_DIR
from routers.user_story_router import list_user_stories
from schemas.test_case_schema import TestCaseGenerateRequest, TestCaseGenerateResponse, TestCaseListResponse
from services.artifact_file_service import write_json_file, unique_filename
from services.journey_map_service import list_journeys
from services.test_case_agent_service import generate_test_cases

router = APIRouter()
TEST_CASES_FILE = STORAGE_DIR / 'test_cases.json'


def _write(items):
    TEST_CASES_FILE.parent.mkdir(parents=True, exist_ok=True)
    TEST_CASES_FILE.write_text(json.dumps(items, indent=2), encoding='utf-8')


def _read():
    if not TEST_CASES_FILE.exists():
        return []
    raw = TEST_CASES_FILE.read_text(encoding='utf-8')
    return json.loads(raw) if raw.strip() else []


@router.post('/test-cases/generate', response_model=TestCaseGenerateResponse)
def generate(payload: TestCaseGenerateRequest):
    journeys = [j for j in list_journeys() if j['journey_id'] in payload.journey_ids]
    stories = [s for s in list_user_stories()['items'] if s['story_id'] in payload.user_story_ids]
    cases = [item.model_dump() for item in generate_test_cases(journeys, stories)]
    generated_at = datetime.now(timezone.utc).isoformat()
    for case in cases:
        case["generated_at"] = generated_at

    _write(cases)
    return {'items': cases, 'count': len(cases)}


@router.get('/test-cases', response_model=TestCaseListResponse)
def list_test_cases():
    items = _read()
    return {'items': items, 'count': len(items)}


def _combined_test_case_payload(items: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], dict] = {}
    for item in items:
        key = (str(item.get("user_story_id") or "US"), str(item.get("journey_id") or ""))
        group = groups.setdefault(key, {"us_id": key[0], "journey_id": key[1], "test_cases": []})
        case = dict(item)
        case.setdefault("test_case_type", "Functional")
        case["test_case_title"] = case.get("test_case_title") or case.get("title", "")
        case["test_case_description"] = case.get("test_case_description") or case.get("description", "")
        case["objective"] = case.get("objective") or case.get("journey_objective", "")
        case["user_story"] = case.get("user_story") or case.get("description") or ""
        case["generated_date"] = case.get("generated_date") or __import__("datetime").date.today().isoformat()
        group["test_cases"].append(case)
    for group in groups.values():
        group["test_cases_count"] = len(group["test_cases"])
    return list(groups.values())
@router.get('/test-cases/download')
def download_test_cases():
    items = _read()
    filename = unique_filename('test_cases', '.json')
    path = write_json_file(filename, _combined_test_case_payload(items))
    return FileResponse(path, filename=filename, media_type='application/json')
