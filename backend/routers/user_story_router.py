import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from core.config import STORAGE_DIR
from schemas.configuration_schema import Configuration
from schemas.user_story_schema import StoryBundle, StorySyncRequest, UserStoryGenerateRequest, UserStoryListResponse
from services.artifact_file_service import write_json_file, unique_filename
from services.jira_agent_service import enrich_story_for_jira, generate_user_stories
from services.jira_client_service import JiraClientError, create_story_issue
from services.journey_map_service import list_journeys
from routers.configuration_router import _read as read_configuration

router = APIRouter()
USER_STORIES_FILE = STORAGE_DIR / 'user_stories.json'
TEST_CASES_FILE = STORAGE_DIR / 'test_cases.json'
TEST_SCRIPTS_FILE = STORAGE_DIR / 'test_scripts.json'


def _read():
    if not USER_STORIES_FILE.exists():
        return []
    raw = USER_STORIES_FILE.read_text(encoding='utf-8')
    return json.loads(raw) if raw.strip() else []



def _replace_all(items):
    USER_STORIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    USER_STORIES_FILE.write_text(json.dumps(items, indent=2), encoding='utf-8')


def _read_json_file(path):
    if not path.exists():
        return []
    raw = path.read_text(encoding='utf-8')
    return json.loads(raw) if raw.strip() else []


def _write_json_file(path, items):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=2), encoding='utf-8')


def _delete_related_artifacts(story_ids: set[str]) -> dict[str, int]:
    test_cases = _read_json_file(TEST_CASES_FILE)
    removed_case_ids = {item.get('test_case_id') for item in test_cases if item.get('user_story_id') in story_ids}
    remaining_cases = [item for item in test_cases if item.get('user_story_id') not in story_ids]
    _write_json_file(TEST_CASES_FILE, remaining_cases)

    test_scripts = _read_json_file(TEST_SCRIPTS_FILE)
    remaining_scripts = [item for item in test_scripts if item.get('test_case_id') not in removed_case_ids and item.get('user_story_id') not in story_ids]
    _write_json_file(TEST_SCRIPTS_FILE, remaining_scripts)

    return {
        'test_cases_deleted': len(test_cases) - len(remaining_cases),
        'test_scripts_deleted': len(test_scripts) - len(remaining_scripts),
    }
def _write(items):
    existing = _read()
    USER_STORIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    USER_STORIES_FILE.write_text(json.dumps(existing + items, indent=2), encoding='utf-8')


@router.post('/user-stories/generate', response_model=StoryBundle)
def generate(payload: UserStoryGenerateRequest):
    journeys = [j for j in list_journeys() if j['journey_id'] in payload.journey_ids]
    bundle = generate_user_stories(journeys)
    generated_at = datetime.now(timezone.utc).isoformat()
    for story in bundle.stories:
        story.generated_at = generated_at
    stories = [story.model_dump() for story in bundle.stories]
    _write(stories)
    return bundle


@router.get('/user-stories', response_model=UserStoryListResponse)
def list_user_stories():
    items = _read()
    return {'items': items, 'count': len(items)}



@router.delete('/user-stories/{story_id}')
def delete_user_story(story_id: str):
    items = _read()
    remaining = [story for story in items if story.get('story_id') != story_id]
    if len(remaining) == len(items):
        raise HTTPException(status_code=404, detail='User story not found')
    _replace_all(remaining)
    cleanup = _delete_related_artifacts({story_id})
    return {'deleted': True, 'story_id': story_id, **cleanup, 'count': len(remaining)}


@router.delete('/user-stories')
def clear_user_stories():
    items = _read()
    story_ids = {story.get('story_id') for story in items if story.get('story_id')}
    _replace_all([])
    cleanup = _delete_related_artifacts(story_ids)
    return {'deleted': True, **cleanup, 'count': 0}

@router.post('/user-stories/sync-jira')
def sync_user_stories_to_jira(payload: StorySyncRequest):
    config_data = read_configuration()
    jira_config = Configuration(**config_data).jira
    items = [story for story in _read() if not payload.story_ids or story.get('story_id') in payload.story_ids]
    if not items:
        raise HTTPException(status_code=400, detail='No user stories available to sync')
    journey_by_id = {journey.get('journey_id'): journey for journey in list_journeys()}
    synced = []
    updated_items = list(_read())
    for story in items:
        story = enrich_story_for_jira(story, journey_by_id.get(story.get('journey_id')))
        acceptance_lines = [criterion.get('ac_text', '') for criterion in story.get('acceptance_criteria', []) if criterion.get('ac_text')]
        try:
            result = create_story_issue(
                jira_config,
                summary=story.get('summary', ''),
                description=story.get('description', ''),
                labels=story.get('labels', []),
                acceptance_criteria=acceptance_lines,
            )
        except JiraClientError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        synced.append({
            'story_id': story.get('story_id', ''),
            'summary': story.get('summary', ''),
            'jira_key': result.get('jira_key', ''),
            'jira_url': result.get('jira_url', ''),
        })
        for persisted in updated_items:
            if persisted.get('story_id') == story.get('story_id'):
                persisted['jira_key'] = result.get('jira_key', '')
                persisted['jira_url'] = result.get('jira_url', '')
                persisted['jira_sync_status'] = 'synced'
                break
    _replace_all(updated_items)
    return {'synced': True, 'message': 'Stories synced to Jira successfully', 'items': synced}


@router.get('/user-stories/download')
def download_user_stories():
    items = _read()
    filename = unique_filename('user_stories', '.json')
    path = write_json_file(filename, items)
    return FileResponse(path, filename=filename, media_type='application/json')