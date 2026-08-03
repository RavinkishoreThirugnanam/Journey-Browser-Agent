import json

from core.config import STORAGE_DIR
from schemas.journey_schema import ExplorationResult, JourneyDetailResponse, JourneyRecord
from services.business_assurance_service import build_business_assurance


JOURNEYS_FILE = STORAGE_DIR / 'journeys.json'
USER_STORIES_FILE = STORAGE_DIR / 'user_stories.json'
TEST_CASES_FILE = STORAGE_DIR / 'test_cases.json'
TEST_SCRIPTS_FILE = STORAGE_DIR / 'test_scripts.json'


def _read_all() -> list[dict]:
    if not JOURNEYS_FILE.exists():
        return []
    raw = JOURNEYS_FILE.read_text(encoding='utf-8')
    return json.loads(raw) if raw.strip() else []


def _write_all(items: list[dict]) -> None:
    JOURNEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    JOURNEYS_FILE.write_text(json.dumps(items, indent=2), encoding='utf-8')


def _read_json_file(path) -> list[dict]:
    if not path.exists():
        return []
    raw = path.read_text(encoding='utf-8')
    return json.loads(raw) if raw.strip() else []


def _write_json_file(path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=2), encoding='utf-8')


def _cascade_delete_for_journeys(journey_ids: set[str]) -> dict[str, int]:
    if not journey_ids:
        return {'user_stories_deleted': 0, 'test_cases_deleted': 0, 'test_scripts_deleted': 0}

    user_stories = _read_json_file(USER_STORIES_FILE)
    removed_story_ids = {story.get('story_id') for story in user_stories if story.get('journey_id') in journey_ids}
    remaining_stories = [story for story in user_stories if story.get('journey_id') not in journey_ids]
    _write_json_file(USER_STORIES_FILE, remaining_stories)

    test_cases = _read_json_file(TEST_CASES_FILE)
    removed_case_ids = {
        case.get('test_case_id')
        for case in test_cases
        if case.get('journey_id') in journey_ids or case.get('user_story_id') in removed_story_ids
    }
    remaining_cases = [
        case
        for case in test_cases
        if case.get('journey_id') not in journey_ids and case.get('user_story_id') not in removed_story_ids
    ]
    _write_json_file(TEST_CASES_FILE, remaining_cases)

    test_scripts = _read_json_file(TEST_SCRIPTS_FILE)
    remaining_scripts = [
        script
        for script in test_scripts
        if script.get('journey_id') not in journey_ids
        and script.get('user_story_id') not in removed_story_ids
        and script.get('test_case_id') not in removed_case_ids
    ]
    _write_json_file(TEST_SCRIPTS_FILE, remaining_scripts)

    return {
        'user_stories_deleted': len(user_stories) - len(remaining_stories),
        'test_cases_deleted': len(test_cases) - len(remaining_cases),
        'test_scripts_deleted': len(test_scripts) - len(remaining_scripts),
    }
def _build_exploration_metadata(exploration: dict, journey: dict) -> dict:
    metadata = exploration.get('exploration_metadata', {}) if isinstance(exploration, dict) else {}
    source_url = journey.get('starting_url') or journey.get('application_url') or journey.get('source_url', '')
    return {
        'app_url': metadata.get('app_url') or source_url,
        'starting_feature': metadata.get('starting_feature') or journey.get('starting_point') or journey.get('journey_title', ''),
        'task_input': metadata.get('task_input') or f'Explore all possible user journeys starting from {source_url}.',
        'depth_level': metadata.get('depth_level'),
        'is_pre_login_scoped': metadata.get('is_pre_login_scoped', False),
        'total_journeys_discovered': metadata.get('total_journeys_discovered', len(exploration.get('journeys', [])) if isinstance(exploration, dict) else 0),
        'exploration_timestamp': metadata.get('exploration_timestamp', ''),
        'viewport': metadata.get('viewport', {}),
        'browser': metadata.get('browser', 'chromium'),
    }


def _normalize_journey(journey: dict, exploration: dict | None = None) -> dict:
    exploration = exploration or {}
    steps = journey.get('steps', []) or []
    events = journey.get('events', []) or []
    if not events and steps:
        for step in steps:
            for interaction in step.get('interactions', []) or []:
                events.append({
                    'event_id': str(interaction.get('sequence_id') or interaction.get('interaction_number') or len(events) + 1),
                    'event': interaction.get('resulted_in') or interaction.get('action') or 'interaction',
                    'page': step.get('page_title') or journey.get('journey_title') or '',
                    'action': interaction.get('action') or '',
                    'url': interaction.get('page_url') or journey.get('starting_url') or journey.get('application_url') or journey.get('source_url', ''),
                    'depth': step.get('depth_level', 0),
                    'timestamp': exploration.get('exploration_metadata', {}).get('exploration_timestamp', ''),
                    'description': interaction.get('resulted_in') or interaction.get('element_label') or interaction.get('selector') or '',
                    'metadata': {
                        'element_type': interaction.get('element_type', ''),
                        'element_label': interaction.get('element_label', ''),
                        'selector': interaction.get('selector', ''),
                        'selector_type': interaction.get('selector_type', ''),
                        'element_id': interaction.get('element_id'),
                        'role': interaction.get('role', ''),
                        'destination_url': interaction.get('destination_url'),
                        'coordinates': interaction.get('coordinates', {}),
                        'network_events': interaction.get('network_events', []),
                        'screenshot_before': interaction.get('screenshot_before'),
                        'screenshot_after': interaction.get('screenshot_after'),
                        'event_timestamp': interaction.get('event_timestamp', ''),
                        'state_before': interaction.get('element_state_before'),
                        'state_after': interaction.get('element_state_after'),
                        'wait_condition': interaction.get('wait_condition', ''),
                        'validation_message': interaction.get('validation_message'),
                    'event_id': interaction.get('event_id', ''),
                    'page_id': interaction.get('page_id', ''),
                    'route': interaction.get('route', ''),
                    'state_fingerprint_before': interaction.get('state_fingerprint_before', ''),
                    'state_fingerprint_after': interaction.get('state_fingerprint_after', ''),
                    'visible_elements': interaction.get('visible_elements', []),
                    },
                })
    exploration_metadata = journey.get('exploration_metadata') or _build_exploration_metadata(exploration, journey)
    normalized = {
        **journey,
        'journey_title': journey.get('journey_title') or journey.get('starting_point') or journey.get('application_url') or journey.get('source_url', ''),
        'starting_point': journey.get('starting_point') or journey.get('journey_title') or journey.get('application_url') or journey.get('source_url', ''),
        'starting_url': journey.get('starting_url') or journey.get('application_url') or journey.get('source_url', ''),
        'outcome': journey.get('outcome', ''),
        'outcome_detail': journey.get('outcome_detail', ''),
        'reasoning': journey.get('reasoning', ''),
        'session_boundary_reached': journey.get('session_boundary_reached', False),
        'session_boundary_url': journey.get('session_boundary_url'),
        'total_depth': journey.get('total_depth', len(steps)),
        'test_hints': journey.get('test_hints', {}),
        'housekeeping_steps': journey.get('housekeeping_steps', []),
        'steps': steps,
        'events': events,
        'exploration_metadata': exploration_metadata,
        'app_url': exploration_metadata.get('app_url') or journey.get('app_url') or journey.get('application_url') or journey.get('source_url', ''),
    }
    normalized['business_assurance'] = build_business_assurance(normalized, exploration_metadata)
    normalized['summary'] = journey.get('summary') or f"{len(steps)} steps captured from {normalized['starting_url']}."
    return normalized


def save_journey(exploration: ExplorationResult | dict) -> ExplorationResult | dict:
    items = _read_all()
    payload = exploration.model_dump() if hasattr(exploration, 'model_dump') else exploration
    items.append(payload)
    _write_all(items)
    return exploration


def _flatten_journeys() -> list[dict]:
    flattened: list[dict] = []
    for exploration in _read_all():
        for journey in exploration.get('journeys', []) if isinstance(exploration, dict) else []:
            flattened.append(_normalize_journey(journey, exploration))
    return flattened


def list_journeys() -> list[dict]:
    return _flatten_journeys()


def get_journey(journey_id: str) -> dict | None:
    for exploration in _read_all():
        if not isinstance(exploration, dict):
            continue
        for journey in exploration.get('journeys', []) or []:
            if journey.get('journey_id') == journey_id:
                return _normalize_journey(journey, exploration)
    return None


def delete_journey(journey_id: str) -> dict:
    result = delete_journeys({journey_id})
    return {
        'deleted': journey_id in result['deleted_ids'],
        'user_stories_deleted': result['user_stories_deleted'],
        'test_cases_deleted': result['test_cases_deleted'],
        'test_scripts_deleted': result['test_scripts_deleted'],
    }


def delete_journeys(journey_ids: set[str]) -> dict:
    requested_ids = {journey_id for journey_id in journey_ids if journey_id}
    items = _read_all()
    updated = []
    deleted_ids: set[str] = set()
    for exploration in items:
        existing_journeys = exploration.get('journeys', [])
        journeys = [j for j in existing_journeys if j.get('journey_id') not in requested_ids]
        deleted_ids.update(
            j.get('journey_id') for j in existing_journeys
            if j.get('journey_id') in requested_ids
        )
        if journeys:
            exploration['journeys'] = journeys
            exploration['exploration_metadata']['total_journeys_discovered'] = len(journeys)
            updated.append(exploration)
    if not deleted_ids:
        return {
            'deleted_count': 0,
            'deleted_ids': [],
            'missing_ids': sorted(requested_ids),
            'user_stories_deleted': 0,
            'test_cases_deleted': 0,
            'test_scripts_deleted': 0,
        }
    _write_all(updated)
    cleanup = _cascade_delete_for_journeys(deleted_ids)
    return {
        'deleted_count': len(deleted_ids),
        'deleted_ids': sorted(deleted_ids),
        'missing_ids': sorted(requested_ids - deleted_ids),
        **cleanup,
    }

def cleanup_orphan_artifacts() -> dict[str, int]:
    journey_ids = {journey.get('journey_id') for journey in _flatten_journeys() if journey.get('journey_id')}

    user_stories = _read_json_file(USER_STORIES_FILE)
    remaining_stories = [story for story in user_stories if story.get('journey_id') in journey_ids]
    removed_story_ids = {story.get('story_id') for story in user_stories if story.get('story_id') and story.get('journey_id') not in journey_ids}
    _write_json_file(USER_STORIES_FILE, remaining_stories)

    story_ids = {story.get('story_id') for story in remaining_stories if story.get('story_id')}
    test_cases = _read_json_file(TEST_CASES_FILE)
    remaining_cases = [
        case
        for case in test_cases
        if (case.get('journey_id') in journey_ids) or (case.get('user_story_id') in story_ids)
    ]
    removed_case_ids = {
        case.get('test_case_id')
        for case in test_cases
        if case.get('test_case_id') and case not in remaining_cases
    }
    _write_json_file(TEST_CASES_FILE, remaining_cases)

    case_ids = {case.get('test_case_id') for case in remaining_cases if case.get('test_case_id')}
    test_scripts = _read_json_file(TEST_SCRIPTS_FILE)
    remaining_scripts = [
        script
        for script in test_scripts
        if (script.get('journey_id') in journey_ids)
        or (script.get('user_story_id') in story_ids)
        or (script.get('test_case_id') in case_ids)
    ]
    _write_json_file(TEST_SCRIPTS_FILE, remaining_scripts)

    return {
        'user_stories_deleted': len(user_stories) - len(remaining_stories),
        'test_cases_deleted': len(test_cases) - len(remaining_cases),
        'test_scripts_deleted': len(test_scripts) - len(remaining_scripts),
        'orphan_story_ids': sorted(removed_story_ids),
        'orphan_case_ids': sorted(removed_case_ids),
    }
def clear_journeys() -> dict:
    journey_ids = {journey.get('journey_id') for journey in _flatten_journeys() if journey.get('journey_id')}
    _write_all([])
    return _cascade_delete_for_journeys(journey_ids)

