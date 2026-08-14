from fastapi.testclient import TestClient

from main import app
from routers.journey_router import _journey_to_detail

client = TestClient(app)


def create_journey():
    response = client.post('/api/v1/exploration/start', json={'application_url': 'https://example.com', 'parameters': {}, 'crawl': {'max_depth': 1, 'max_pages': 4, 'follow_links': False}})
    assert response.status_code == 200
    return response.json()['journey_id']


def test_health():
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'


def test_lightweight_journey_detail_keeps_replay_and_defers_heavy_evidence():
    journey = {
        'journey_id': 'journey-lightweight',
        'steps': [{
            'interactions': [{
                'action': 'click',
                'selector': '#target',
                'replay': {'selector': '#target'},
                'dom_snapshot_before': '<html>large</html>',
                'screenshot_after': 'data:image/png;base64,large',
                'network_events': [{'url': 'https://example.com'}],
                'visible_elements': [{'label': 'Target'}],
            }],
        }],
        'events': [{'action': 'click'}, {'action': 'navigate'}],
        'test_hints': {
            'live_stream_key': 'stream-key',
            'candidate_ledger': [{'large': 'payload'}],
            'page_ids': ['page-1'],
            'event_ids': ['event-1'],
        },
    }

    detail = _journey_to_detail(journey, include_evidence=False)

    interaction = detail['steps'][0]['interactions'][0]
    assert detail['event_count'] == 2
    assert detail['events'] == []
    assert detail['test_hints'] == {'live_stream_key': 'stream-key'}
    assert interaction['selector'] == '#target'
    assert interaction['replay'] == {'selector': '#target'}
    assert 'dom_snapshot_before' not in interaction
    assert 'screenshot_after' not in interaction
    assert 'network_events' not in interaction
    assert 'visible_elements' not in interaction


def test_page_evidence_detail_deduplicates_large_capture_fields_per_page():
    journey = {
        'journey_id': 'journey-evidence',
        'steps': [{
            'step_number': 1,
            'depth_level': 0,
            'page_title': 'Example',
            'page_url': 'https://example.com/page',
            'interactions': [
                {
                    'action': 'inspect',
                    'dom_snapshot_after': '<html>first</html>',
                    'screenshot_after': 'first-image',
                    'visible_elements': [{'label': 'First'}],
                    'network_events': [{'url': 'large'}],
                },
                {
                    'action': 'click',
                    'dom_snapshot_after': '<html>latest</html>',
                    'screenshot_after': 'latest-image',
                    'visible_elements': [{'label': 'Latest'}],
                    'network_events': [{'url': 'large'}],
                },
            ],
        }],
        'events': [],
    }

    detail = _journey_to_detail(journey, include_evidence=True)

    first, latest = detail['steps'][0]['interactions']
    assert 'dom_snapshot_after' not in first
    assert 'screenshot_after' not in first
    assert 'network_events' not in first
    assert latest['dom_snapshot_after'] == '<html>latest</html>'
    assert latest['screenshot_after'] == 'latest-image'
    assert latest['visible_elements'] == [{'label': 'Latest'}]
    assert 'network_events' not in latest


def test_configuration_round_trip():
    payload = {
        'jira': {'base_url': 'https://jira.example.com', 'project_key': 'PRJ', 'username': 'user', 'api_token': 'token', 'auth_type': 'basic', 'issue_type': 'Story'},
        'llm': {'provider': 'OpenAI', 'model': 'gpt-4o-mini', 'api_endpoint': 'https://api.openai.com/v1', 'auth_token': 'secret', 'temperature': 0.2},
        'application': {'base_url': 'https://app.example.com', 'environment': 'test', 'default_project': 'Demo', 'global_parameters': {}},
    }
    save = client.post('/api/v1/configuration', json=payload)
    assert save.status_code == 200
    fetch = client.get('/api/v1/configuration')
    assert fetch.status_code == 200
    assert fetch.json()['llm']['model'] == 'gpt-4o-mini'


def test_llm_models():
    response = client.get('/api/v1/configuration/llm-models')
    assert response.status_code == 200
    assert any(model['provider'] == 'OpenAI' for model in response.json()['models'])


def test_exploration_and_journey_flow():
    journey_id = create_journey()
    journeys = client.get('/api/v1/journeys')
    assert journeys.status_code == 200
    assert any(item['journey_id'] == journey_id for item in journeys.json())
    payload = next(item for item in journeys.json() if item['journey_id'] == journey_id)
    assert payload['events']
    viz = client.post('/api/v1/journeys/visualize', json={'journey_id': journey_id})
    assert viz.status_code == 200
    assert 'flowchart TD' in viz.json()['mermaid']
    consolidated = client.post('/api/v1/journeys/visualize', json={
        'mode': 'consolidated',
        'journey_ids': [journey_id],
        'root_feature': 'Account Settings',
    })
    assert consolidated.status_code == 200
    assert consolidated.json()['mode'] == 'consolidated'
    assert consolidated.json()['root_feature'] == 'Account Settings'
    assert '["Account Settings"]' in consolidated.json()['mermaid']


def test_user_story_generation_flow():
    journey_id = create_journey()
    response = client.post('/api/v1/user-stories/generate', json={'journey_ids': [journey_id]})
    assert response.status_code == 200
    body = response.json()
    assert 'stories' in body
    assert len(body['stories']) >= 1
    assert body['stories'][0]['summary'].startswith('US-01')
    assert len(body['stories'][0]['acceptance_criteria']) == 4


def test_test_case_generation_flow():
    journey_id = create_journey()
    stories = client.post('/api/v1/user-stories/generate', json={'journey_ids': [journey_id]}).json()['stories']
    story_id = stories[0]['story_id']
    response = client.post('/api/v1/test-cases/generate', json={'journey_ids': [journey_id], 'user_story_ids': [story_id]})
    assert response.status_code == 200
    body = response.json()
    assert body['count'] >= 1
    assert body['items'][0]['journey_id'] == journey_id


def test_test_script_generation_flow():
    journey_id = create_journey()
    story_bundle = client.post('/api/v1/user-stories/generate', json={'journey_ids': [journey_id]}).json()['stories']
    story = story_bundle[0]
    case = client.post('/api/v1/test-cases/generate', json={'journey_ids': [journey_id], 'user_story_ids': [story['story_id']]}).json()['items'][0]
    response = client.post('/api/v1/test-scripts/generate', json={'test_case_ids': [case['test_case_id']]})
    assert response.status_code == 200
    body = response.json()
    assert body['count'] >= 1
    assert body['items'][0]['test_case_id'] == case['test_case_id']

def test_user_story_generation_retains_journey_ids():
    journey_a = create_journey()
    journey_b = create_journey()
    response = client.post('/api/v1/user-stories/generate', json={'journey_ids': [journey_a, journey_b]})
    assert response.status_code == 200
    body = response.json()
    assert len(body['stories']) >= 2
    assert {story['journey_id'] for story in body['stories']} >= {journey_a, journey_b}

def test_test_case_generation_syncs_to_jira_when_configured():
    payload = {
        'jira': {'base_url': 'https://jira.example.com', 'project_key': 'PRJ', 'username': 'user', 'api_token': 'token', 'auth_type': 'basic', 'issue_type': 'Story', 'test_case_issue_type': 'Test'},
        'llm': {'provider': 'OpenAI', 'model': 'gpt-4o-mini', 'api_endpoint': 'https://api.openai.com/v1', 'auth_token': 'secret', 'temperature': 0.2},
        'application': {'base_url': 'https://app.example.com', 'environment': 'test', 'default_project': 'Demo', 'global_parameters': {}},
    }
    client.post('/api/v1/configuration', json=payload)
    journey_id = create_journey()
    stories = client.post('/api/v1/user-stories/generate', json={'journey_ids': [journey_id]}).json()['stories']
    story_id = stories[0]['story_id']
    response = client.post('/api/v1/test-cases/generate', json={'journey_ids': [journey_id], 'user_story_ids': [story_id]})
    assert response.status_code == 200
    body = response.json()
    assert body['count'] >= 1
    assert body['items'][0]['journey_id'] == journey_id
    assert body['items'][0].get('jira_key') is not None

def test_exploration_payload_matches_nested_sample_shape(monkeypatch):
    from services import browser_agent_service as bas

    def fake_crawl(*args, **kwargs):
        return [
            bas.JourneyStep(
                step_number=1,
                depth_level=0,
                page_title='Home',
                page_url='https://example.com/',
                interactions=[
                    bas.Interaction(
                        sequence_id=1,
                        interaction_number=1,
                        element_type='link',
                        element_label='Tickets & Parks',
                        selector="[name='tickets']",
                        selector_type='css',
                        action='click',
                        resulted_in='new_page:https://example.com/admission/',
                        wait_condition='url_change',
                        parent_component='main_navigation',
                    )
                ],
            )
        ], ['Loaded https://example.com/'], []

    monkeypatch.setattr(bas, '_crawl_with_playwright', fake_crawl)
    result = bas.explore_application('https://example.com/', {}, {'max_depth': 1, 'max_pages': 1, 'follow_links': False})
    assert result.exploration_metadata.app_url == 'https://example.com/'
    assert result.journeys[0].journey_id
    assert result.journeys[0].steps[0].interactions[0].element_label == 'Tickets & Parks'
    assert result.journeys[0].steps[0].interactions[0].resulted_in.startswith('new_page:')


def test_journey_list_flattens_nested_exploration_bundle(monkeypatch):
    from services import journey_map_service as jms

    sample = [{
        'exploration_metadata': {
            'app_url': 'https://example.com/',
            'starting_feature': 'Home',
            'task_input': 'Explore the home journey',
            'browser': 'chromium',
        },
        'journeys': [{
            'journey_id': 'JRN-001',
            'journey_title': 'Home Flow',
            'starting_point': 'Home',
            'starting_url': 'https://example.com/',
            'outcome': 'Exploration Complete',
            'outcome_detail': 'OK',
            'reasoning': 'Loaded home page',
            'session_boundary_reached': False,
            'session_boundary_url': None,
            'total_depth': 1,
            'test_hints': {'requires_auth': False},
            'housekeeping_steps': [],
            'steps': [],
        }],
    }]

    monkeypatch.setattr(jms, '_iter_all', lambda: iter(sample))
    journeys = jms.list_journeys()
    assert len(journeys) == 1
    assert journeys[0]['journey_id'] == 'JRN-001'
    assert journeys[0]['starting_url'] == 'https://example.com/'
    assert journeys[0]['app_url'] == 'https://example.com/'


def test_compact_journey_list_keeps_selection_fields_without_heavy_evidence(monkeypatch):
    from services import journey_map_service as jms

    sample = [{
        'exploration_metadata': {'app_url': 'https://example.com/', 'exploration_timestamp': '2026-08-12T10:00:00Z'},
        'journeys': [{
            'journey_id': 'JRN-REPLAY',
            'journey_title': 'Replay Flow',
            'starting_url': 'https://example.com/',
            'outcome': 'Exploration Complete',
            'steps': [{
                'step_number': 1,
                'interactions': [{
                    'action': 'click',
                    'dom_snapshot_after': '<html>' + ('x' * 10000) + '</html>',
                }],
            }],
        }],
    }]

    monkeypatch.setattr(jms, '_iter_all', lambda: iter(sample))
    monkeypatch.setattr(jms, 'JOURNEYS_INDEX_FILE', jms.STORAGE_DIR / '.missing-test-journeys.index.json')
    monkeypatch.setattr(jms, '_write_json_file', lambda _path, _items: None)
    summaries = jms.list_journey_summaries()

    assert summaries[0]['journey_id'] == 'JRN-REPLAY'
    assert summaries[0]['interaction_count'] == 1
    assert 'steps' not in summaries[0]
    assert 'events' not in summaries[0]
