import json

from core.config import STORAGE_DIR
from schemas.journey_schema import ExplorationResult, JourneyDetailResponse, JourneyRecord


JOURNEYS_FILE = STORAGE_DIR / 'journeys.json'


def _read_all() -> list[dict]:
    if not JOURNEYS_FILE.exists():
        return []
    raw = JOURNEYS_FILE.read_text(encoding='utf-8')
    return json.loads(raw) if raw.strip() else []


def _write_all(items: list[dict]) -> None:
    JOURNEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    JOURNEYS_FILE.write_text(json.dumps(items, indent=2), encoding='utf-8')


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
    }
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


def delete_journey(journey_id: str) -> bool:
    items = _read_all()
    updated = []
    removed = False
    for exploration in items:
        journeys = [j for j in exploration.get('journeys', []) if j.get('journey_id') != journey_id]
        if len(journeys) != len(exploration.get('journeys', [])):
            removed = True
        if journeys:
            exploration['journeys'] = journeys
            exploration['exploration_metadata']['total_journeys_discovered'] = len(journeys)
            updated.append(exploration)
    if not removed:
        return False
    _write_all(updated)
    return True


def clear_journeys() -> None:
    _write_all([])
