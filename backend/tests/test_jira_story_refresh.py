from copy import deepcopy

from routers import user_story_router
from services.jira_client_service import _extract_description_and_acceptance


def test_extracts_acceptance_criteria_from_jira_adf():
    document = {
        'type': 'doc',
        'version': 1,
        'content': [
            {'type': 'paragraph', 'content': [{'type': 'text', 'text': 'As a user, I need the latest workflow.'}]},
            {'type': 'paragraph', 'content': [{'type': 'text', 'text': 'Acceptance Criteria'}]},
            {
                'type': 'bulletList',
                'content': [
                    {'type': 'listItem', 'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': 'The latest Jira criteria is used.'}]}]},
                    {'type': 'listItem', 'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': 'Journey traceability is preserved.'}]}]},
                ],
            },
        ],
    }

    description, criteria, found = _extract_description_and_acceptance(document)

    assert found is True
    assert description == 'As a user, I need the latest workflow.'
    assert criteria == [
        'The latest Jira criteria is used.',
        'Journey traceability is preserved.',
    ]


def test_refresh_updates_business_fields_and_preserves_local_traceability(monkeypatch):
    stored = [{
        'story_id': 'STORY-1',
        'journey_id': 'JOURNEY-1',
        'summary': 'Local summary',
        'description': 'Local description',
        'acceptance_criteria': [{'ac_type': 'functional', 'ac_text': 'Old criterion', 'ac_id': 'AC-1'}],
        'labels': ['local'],
        'epic': 'Epic',
        'module': 'Module',
        'component': 'Browser Agent',
        'jira_key': 'PRJ-10',
        'jira_url': 'https://jira.example.com/browse/PRJ-10',
        'jira_sync_status': 'synced',
    }]
    saved = {}

    monkeypatch.setattr(user_story_router, '_read', lambda: deepcopy(stored))
    monkeypatch.setattr(user_story_router, '_replace_all', lambda items: saved.setdefault('items', deepcopy(items)))
    monkeypatch.setattr(user_story_router, 'read_configuration', lambda: {
        'jira': {'base_url': 'https://jira.example.com', 'project_key': 'PRJ'},
        'llm': {},
        'application': {},
    })
    monkeypatch.setattr(user_story_router, 'get_issue', lambda config, key: {
        'jira_key': key,
        'jira_url': 'https://jira.example.com/browse/PRJ-10',
        'summary': 'Latest Jira summary',
        'description': 'Latest Jira description',
        'acceptance_criteria': ['Latest Jira criterion'],
        'acceptance_criteria_found': True,
        'labels': ['jira'],
        'updated': '2026-08-06T10:00:00.000+0000',
    })

    result = user_story_router.refresh_user_stories_from_jira(['STORY-1'])
    refreshed = saved['items'][0]

    assert result['updated'] == 1
    assert result['failed'] == 0
    assert refreshed['story_id'] == 'STORY-1'
    assert refreshed['journey_id'] == 'JOURNEY-1'
    assert refreshed['summary'] == 'Latest Jira summary'
    assert refreshed['description'] == 'Latest Jira description'
    assert refreshed['acceptance_criteria'][0]['ac_text'] == 'Latest Jira criterion'
    assert refreshed['acceptance_criteria'][0]['ac_id'] == 'AC-1'
    assert refreshed['labels'] == ['jira']
    assert refreshed['jira_sync_status'] == 'updated_from_jira'
    assert refreshed['jira_last_refreshed_at']