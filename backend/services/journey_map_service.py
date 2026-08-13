import json
import re
from uuid import uuid4

try:
    import ijson
except ImportError:  # pragma: no cover - compatibility for minimal local test environments
    ijson = None

from core.config import STORAGE_DIR
from schemas.journey_schema import ExplorationResult, JourneyDetailResponse, JourneyRecord
from services.business_assurance_service import build_business_assurance


JOURNEYS_FILE = STORAGE_DIR / 'journeys.json'
JOURNEY_BUNDLES_DIR = STORAGE_DIR / 'journey_bundles'
JOURNEY_RECORDS_DIR = STORAGE_DIR / 'journey_records'
JOURNEYS_INDEX_FILE = STORAGE_DIR / 'journeys.index.json'
JOURNEYS_INDEX_VERSION = 4
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
    JOURNEYS_INDEX_FILE.unlink(missing_ok=True)


def _iter_legacy_bundles():
    if JOURNEYS_FILE.exists() and JOURNEYS_FILE.stat().st_size:
        if ijson is not None:
            with JOURNEYS_FILE.open('rb') as source:
                yield from ijson.items(source, 'item')
        else:
            yield from _read_all()


def _iter_all():
    """Stream legacy bundles and then read newer file-per-run bundles."""
    yield from _iter_legacy_bundles()
    if JOURNEY_BUNDLES_DIR.exists():
        for path in sorted(JOURNEY_BUNDLES_DIR.glob('*.json')):
            try:
                payload = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                yield payload


def _read_json_file(path) -> list[dict]:
    if not path.exists():
        return []
    raw = path.read_text(encoding='utf-8')
    return json.loads(raw) if raw.strip() else []


def _write_json_file(path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=2), encoding='utf-8')


def _journey_record_path(journey_id: str):
    safe_id = re.sub(r'[^A-Za-z0-9_.-]+', '_', str(journey_id or ''))
    return JOURNEY_RECORDS_DIR / f'{safe_id}.json'


def _write_journey_record(exploration: dict, journey: dict) -> None:
    journey_id = str(journey.get('journey_id') or '')
    if not journey_id:
        return
    JOURNEY_RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    _journey_record_path(journey_id).write_text(json.dumps({
        'exploration_metadata': exploration.get('exploration_metadata', {}),
        'journey': journey,
    }, indent=2), encoding='utf-8')


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
    payload = exploration.model_dump() if hasattr(exploration, 'model_dump') else exploration
    JOURNEY_BUNDLES_DIR.mkdir(parents=True, exist_ok=True)
    metadata = payload.get('exploration_metadata', {}) if isinstance(payload, dict) else {}
    bundle_id = str(metadata.get('exploration_id') or uuid4())
    bundle_path = JOURNEY_BUNDLES_DIR / f'{bundle_id}.json'
    bundle_path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    if isinstance(payload, dict):
        for journey in payload.get('journeys', []) or []:
            if isinstance(journey, dict):
                _write_journey_record(payload, journey)
    JOURNEYS_INDEX_FILE.unlink(missing_ok=True)
    return exploration


def _flatten_journeys() -> list[dict]:
    flattened: list[dict] = []
    for exploration in _iter_all():
        for journey in exploration.get('journeys', []) if isinstance(exploration, dict) else []:
            flattened.append(_normalize_journey(journey, exploration))
    return flattened


def list_journeys() -> list[dict]:
    return _flatten_journeys()


def list_journey_summaries() -> list[dict]:
    """Return list-page fields without sending large DOM and screenshot evidence."""
    if JOURNEYS_INDEX_FILE.exists():
        try:
            cached = json.loads(JOURNEYS_INDEX_FILE.read_text(encoding='utf-8'))
            if isinstance(cached, dict) and cached.get('version') == JOURNEYS_INDEX_VERSION and isinstance(cached.get('items'), list):
                return cached['items']
        except (OSError, json.JSONDecodeError):
            pass
    summaries: list[dict] = []
    for exploration in _iter_all():
        if not isinstance(exploration, dict):
            continue
        for journey in exploration.get('journeys', []) or []:
            if not isinstance(journey, dict):
                continue
            _write_journey_record(exploration, journey)
            metadata = journey.get('exploration_metadata') or _build_exploration_metadata(exploration, journey)
            steps = journey.get('steps', []) or []
            interaction_count = sum(
                len(step.get('interactions', []) or [])
                for step in steps
                if isinstance(step, dict)
            )
            starting_url = journey.get('starting_url') or journey.get('application_url') or journey.get('source_url', '')
            summaries.append({
                'journey_id': journey.get('journey_id', ''),
                'journey_title': journey.get('journey_title') or journey.get('starting_point') or starting_url,
                'starting_point': journey.get('starting_point') or journey.get('journey_title') or starting_url,
                'starting_url': starting_url,
                'outcome': journey.get('outcome', ''),
                'outcome_detail': journey.get('outcome_detail', ''),
                'total_depth': journey.get('total_depth', len(steps)),
                'exploration_metadata': metadata,
                'app_url': metadata.get('app_url') or starting_url,
                'step_count': len(steps),
                'interaction_count': interaction_count,
                'summary': journey.get('summary') or f"{len(steps)} steps captured from {starting_url}.",
            })
    _write_json_file(JOURNEYS_INDEX_FILE, {'version': JOURNEYS_INDEX_VERSION, 'items': summaries})
    return summaries


def get_journey(journey_id: str) -> dict | None:
    record_path = _journey_record_path(journey_id)
    if record_path.exists():
        try:
            record = json.loads(record_path.read_text(encoding='utf-8'))
            journey = record.get('journey') if isinstance(record, dict) else None
            if isinstance(journey, dict):
                return _normalize_journey(journey, {'exploration_metadata': record.get('exploration_metadata', {})})
        except (OSError, json.JSONDecodeError):
            pass
    for exploration in _iter_all():
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
    deleted_ids: set[str] = set()

    def filtered_exploration(exploration: dict) -> dict | None:
        existing = exploration.get('journeys', []) or []
        kept = []
        for journey in existing:
            journey_id = journey.get('journey_id') if isinstance(journey, dict) else None
            if journey_id in requested_ids:
                deleted_ids.add(journey_id)
            else:
                kept.append(journey)
        if not kept:
            return None
        exploration['journeys'] = kept
        metadata = exploration.setdefault('exploration_metadata', {})
        metadata['total_journeys_discovered'] = len(kept)
        return exploration

    # Rewrite the legacy array incrementally instead of loading its large DOM
    # evidence payload into memory.
    if JOURNEYS_FILE.exists():
        temporary = JOURNEYS_FILE.with_name(f'{JOURNEYS_FILE.name}.{uuid4().hex}.tmp')
        with temporary.open('w', encoding='utf-8') as target:
            target.write('[\n')
            first = True
            for exploration in _iter_legacy_bundles():
                filtered = filtered_exploration(exploration)
                if filtered is None:
                    continue
                if not first:
                    target.write(',\n')
                json.dump(filtered, target, indent=2)
                first = False
            target.write('\n]\n')
        temporary.replace(JOURNEYS_FILE)

    # Newer explorations are isolated by bundle, so deleting one never
    # requires rewriting unrelated journey evidence.
    if JOURNEY_BUNDLES_DIR.exists():
        for path in JOURNEY_BUNDLES_DIR.glob('*.json'):
            try:
                exploration = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError):
                continue
            original_count = len(exploration.get('journeys', []) or [])
            filtered = filtered_exploration(exploration)
            if filtered is None:
                path.unlink(missing_ok=True)
            elif len(filtered.get('journeys', [])) != original_count:
                path.write_text(json.dumps(filtered, indent=2), encoding='utf-8')
    if not deleted_ids:
        return {
            'deleted_count': 0,
            'deleted_ids': [],
            'missing_ids': sorted(requested_ids),
            'user_stories_deleted': 0,
            'test_cases_deleted': 0,
            'test_scripts_deleted': 0,
        }
    JOURNEYS_INDEX_FILE.unlink(missing_ok=True)
    for journey_id in deleted_ids:
        _journey_record_path(journey_id).unlink(missing_ok=True)
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
    journey_ids = {item.get('journey_id') for item in list_journey_summaries() if item.get('journey_id')}
    _write_all([])
    for directory in (JOURNEY_BUNDLES_DIR, JOURNEY_RECORDS_DIR):
        if directory.exists():
            for path in directory.glob('*.json'):
                path.unlink(missing_ok=True)
    JOURNEYS_INDEX_FILE.unlink(missing_ok=True)
    return _cascade_delete_for_journeys(journey_ids)

