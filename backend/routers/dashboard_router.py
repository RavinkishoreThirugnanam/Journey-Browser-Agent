import json
from pathlib import Path

from fastapi import APIRouter

from core.config import STORAGE_DIR
from services.journey_map_service import list_journey_summaries

router = APIRouter()


def _read_items(path: Path) -> list[dict]:
    if not path.exists():
        return []
    raw = path.read_text(encoding='utf-8')
    value = json.loads(raw) if raw.strip() else []
    return value if isinstance(value, list) else []


def _timestamp(item: dict, fallback: int) -> tuple[float, int]:
    from datetime import datetime

    for key in ('generated_at', 'updated_at', 'created_at', 'timestamp', 'captured_at'):
        value = item.get(key)
        if not value:
            continue
        try:
            return datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp(), fallback
        except (TypeError, ValueError):
            continue
    return 0.0, fallback


def _newest(items: list[dict], limit: int = 3) -> list[dict]:
    indexed = list(enumerate(items))
    indexed.sort(key=lambda pair: _timestamp(pair[1], pair[0]), reverse=True)
    return [item for _, item in indexed[:limit]]


@router.get('/dashboard/summary')
def dashboard_summary():
    journeys = [{
        'journey_id': journey.get('journey_id') or '',
        'journey_title': journey.get('journey_title') or journey.get('starting_point') or 'Untitled journey',
        'source_url': journey.get('starting_url') or journey.get('app_url') or '',
        'step_count': journey.get('step_count', 0),
        'captured_at': (journey.get('exploration_metadata') or {}).get('exploration_timestamp') or '',
    } for journey in list_journey_summaries() if isinstance(journey, dict)]

    journey_ids = {item['journey_id'] for item in journeys if item.get('journey_id')}
    raw_stories = _read_items(STORAGE_DIR / 'user_stories.json')
    stories = [{
        'story_id': item.get('story_id') or '',
        'journey_id': item.get('journey_id') or '',
        'summary': item.get('summary') or 'Untitled user story',
        'generated_at': item.get('generated_at') or '',
    } for item in raw_stories if isinstance(item, dict) and item.get('journey_id') in journey_ids]

    story_ids = {item['story_id'] for item in stories if item.get('story_id')}
    raw_cases = _read_items(STORAGE_DIR / 'test_cases.json')
    cases = [{
        'test_case_id': item.get('test_case_id') or '',
        'journey_id': item.get('journey_id') or '',
        'user_story_id': item.get('user_story_id') or '',
        'title': item.get('title') or 'Untitled test case',
        'generated_at': item.get('generated_at') or '',
    } for item in raw_cases if isinstance(item, dict) and (
        item.get('journey_id') in journey_ids or item.get('user_story_id') in story_ids
    )]

    case_ids = {item['test_case_id'] for item in cases if item.get('test_case_id')}
    raw_scripts = _read_items(STORAGE_DIR / 'test_scripts.json')
    scripts = [{
        'script_id': item.get('script_id') or '',
        'journey_id': item.get('journey_id') or '',
        'user_story_id': item.get('user_story_id') or '',
        'test_case_id': item.get('test_case_id') or '',
        'feature_filename': item.get('feature_filename') or '',
        'generated_at': item.get('generated_at') or '',
    } for item in raw_scripts if isinstance(item, dict) and (
        item.get('journey_id') in journey_ids
        or item.get('user_story_id') in story_ids
        or item.get('test_case_id') in case_ids
    )]

    return {
        'counts': {
            'journeys': len(journeys),
            'stories': len(stories),
            'cases': len(cases),
            'scripts': len(scripts),
        },
        'latest': {
            'journeys': _newest(journeys),
            'stories': _newest(stories),
            'cases': _newest(cases),
            'scripts': _newest(scripts),
        },
    }
