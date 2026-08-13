from fastapi.testclient import TestClient
import json
from pathlib import Path

from main import app
from routers import journey_router
from services import journey_map_service


def test_bulk_delete_removes_requested_journeys_once_and_reports_missing(monkeypatch):
    stored = [{
        'exploration_metadata': {'total_journeys_discovered': 2},
        'journeys': [
            {'journey_id': 'JRN-keep'},
            {'journey_id': 'JRN-delete'},
        ],
    }]
    cascades = []
    test_file = Path('storage/test-delete-journeys.json')
    test_index = Path('storage/test-delete-journeys.index.json')
    test_records = Path('storage/test-delete-records')
    test_bundles = Path('storage/test-delete-bundles')
    test_file.write_text(json.dumps(stored), encoding='utf-8')
    monkeypatch.setattr(journey_map_service, 'JOURNEYS_FILE', test_file)
    monkeypatch.setattr(journey_map_service, 'JOURNEYS_INDEX_FILE', test_index)
    monkeypatch.setattr(journey_map_service, 'JOURNEY_RECORDS_DIR', test_records)
    monkeypatch.setattr(journey_map_service, 'JOURNEY_BUNDLES_DIR', test_bundles)
    monkeypatch.setattr(
        journey_map_service,
        '_cascade_delete_for_journeys',
        lambda ids: cascades.append(ids) or {
            'user_stories_deleted': 1,
            'test_cases_deleted': 2,
            'test_scripts_deleted': 3,
        },
    )

    try:
        result = journey_map_service.delete_journeys({'JRN-delete', 'JRN-missing'})
        rewritten = json.loads(test_file.read_text(encoding='utf-8'))
    finally:
        test_file.unlink(missing_ok=True)
        test_index.unlink(missing_ok=True)

    assert result['deleted_count'] == 1
    assert result['deleted_ids'] == ['JRN-delete']
    assert result['missing_ids'] == ['JRN-missing']
    assert rewritten[0]['journeys'] == [{'journey_id': 'JRN-keep'}]
    assert rewritten[0]['exploration_metadata']['total_journeys_discovered'] == 1
    assert cascades == [{'JRN-delete'}]


def test_bulk_delete_endpoint_accepts_multiple_journey_ids(monkeypatch):
    monkeypatch.setattr(
        journey_router,
        'delete_journeys',
        lambda ids: {
            'deleted_count': len(ids),
            'deleted_ids': sorted(ids),
            'missing_ids': [],
            'user_stories_deleted': 0,
            'test_cases_deleted': 0,
            'test_scripts_deleted': 0,
        },
    )
    client = TestClient(app)

    response = client.post(
        '/api/v1/journeys/delete-selected',
        json={'journey_ids': ['JRN-2', 'JRN-1']},
    )

    assert response.status_code == 200
    assert response.json()['deleted_count'] == 2
    assert response.json()['deleted_ids'] == ['JRN-1', 'JRN-2']


def test_bulk_delete_endpoint_rejects_an_empty_selection():
    client = TestClient(app)

    response = client.post('/api/v1/journeys/delete-selected', json={'journey_ids': []})

    assert response.status_code == 422
