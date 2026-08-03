from fastapi.testclient import TestClient

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
    writes = []
    cascades = []
    monkeypatch.setattr(journey_map_service, '_read_all', lambda: stored)
    monkeypatch.setattr(journey_map_service, '_write_all', lambda value: writes.append(value))
    monkeypatch.setattr(
        journey_map_service,
        '_cascade_delete_for_journeys',
        lambda ids: cascades.append(ids) or {
            'user_stories_deleted': 1,
            'test_cases_deleted': 2,
            'test_scripts_deleted': 3,
        },
    )

    result = journey_map_service.delete_journeys({'JRN-delete', 'JRN-missing'})

    assert result['deleted_count'] == 1
    assert result['deleted_ids'] == ['JRN-delete']
    assert result['missing_ids'] == ['JRN-missing']
    assert writes[0][0]['journeys'] == [{'journey_id': 'JRN-keep'}]
    assert writes[0][0]['exploration_metadata']['total_journeys_discovered'] == 1
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