import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from core.config import STORAGE_DIR
from routers.configuration_router import _read as read_configuration
from routers.user_story_router import list_user_stories
from schemas.configuration_schema import Configuration
from schemas.test_case_schema import TestCaseGenerateRequest, TestCaseGenerateResponse, TestCaseListResponse
from services.artifact_file_service import write_json_file, unique_filename
from services.jira_client_service import JiraClientError, create_test_case_issue
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

    config_data = read_configuration()
    jira_config = Configuration(**config_data).jira
    jira_enabled = bool(jira_config.base_url and jira_config.project_key and jira_config.username and jira_config.api_token)
    synced_count = 0
    failed_count = 0

    if jira_enabled:
        for case in cases:
            try:
                result = create_test_case_issue(
                    jira_config,
                    summary=case.get('title', ''),
                    description=case.get('description', ''),
                    labels=['test-case', 'journey', 'automation'],
                    acceptance_criteria=case.get('expected_results', []),
                )
            except JiraClientError as exc:
                case['sync_status'] = 'local'
                case['sync_error'] = str(exc)
                failed_count += 1
                continue

            case['jira_key'] = result.get('jira_key', '')
            case['jira_url'] = result.get('jira_url', '')
            case['jira_issue_type'] = result.get('jira_issue_type', '')
            case['sync_status'] = 'jira_synced'
            case['sync_error'] = ''
            synced_count += 1
    else:
        failed_count = len(cases)

    _write(cases)
    return {'items': cases, 'count': len(cases), 'jira_synced_count': synced_count, 'jira_failed_count': failed_count}


@router.get('/test-cases', response_model=TestCaseListResponse)
def list_test_cases():
    items = _read()
    return {'items': items, 'count': len(items)}


@router.get('/test-cases/download')
def download_test_cases():
    items = _read()
    filename = unique_filename('test_cases', '.json')
    path = write_json_file(filename, items)
    return FileResponse(path, filename=filename, media_type='application/json')
