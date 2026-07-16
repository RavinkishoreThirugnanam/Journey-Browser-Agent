import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from core.config import STORAGE_DIR
from schemas.configuration_schema import Configuration
from schemas.user_story_schema import StoryBundle, StorySyncRequest, UserStoryGenerateRequest, UserStoryListResponse
from services.artifact_file_service import write_json_file, unique_filename
from services.jira_agent_service import generate_user_stories
from services.jira_client_service import JiraClientError, create_story_issue
from services.journey_map_service import list_journeys
from routers.configuration_router import _read as read_configuration

router = APIRouter()
USER_STORIES_FILE = STORAGE_DIR / 'user_stories.json'


def _read():
    if not USER_STORIES_FILE.exists():
        return []
    raw = USER_STORIES_FILE.read_text(encoding='utf-8')
    return json.loads(raw) if raw.strip() else []


def _write(items):
    existing = _read()
    USER_STORIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    USER_STORIES_FILE.write_text(json.dumps(existing + items, indent=2), encoding='utf-8')


@router.post('/user-stories/generate', response_model=StoryBundle)
def generate(payload: UserStoryGenerateRequest):
    journeys = [j for j in list_journeys() if j['journey_id'] in payload.journey_ids]
    bundle = generate_user_stories(journeys)
    stories = [story.model_dump() for story in bundle.stories]
    _write(stories)
    return bundle


@router.get('/user-stories', response_model=UserStoryListResponse)
def list_user_stories():
    items = _read()
    return {'items': items, 'count': len(items)}


@router.post('/user-stories/sync-jira')
def sync_user_stories_to_jira(payload: StorySyncRequest):
    config_data = read_configuration()
    jira_config = Configuration(**config_data).jira
    items = [story for story in _read() if not payload.story_ids or story.get('story_id') in payload.story_ids]
    if not items:
        raise HTTPException(status_code=400, detail='No user stories available to sync')
    synced = []
    for story in items:
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
    return {'synced': True, 'message': 'Stories synced to Jira successfully', 'items': synced}


@router.get('/user-stories/download')
def download_user_stories():
    items = _read()
    filename = unique_filename('user_stories', '.json')
    path = write_json_file(filename, items)
    return FileResponse(path, filename=filename, media_type='application/json')