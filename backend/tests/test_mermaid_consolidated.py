from services.mermaid_agent_service import journeys_to_mermaid


def test_consolidated_mermaid_merges_shared_scenario_and_preserves_outcomes():
    journeys = [
        {
            'journey_title': 'Family & Friends List',
            'outcome': 'completed',
            'steps': [{'interactions': [
                {'action': 'click', 'element_label': 'Add Guest'},
                {'action': 'click', 'element_label': 'Search for Guest'},
                {'action': 'fill', 'element_label': 'Guest Details'},
                {'action': 'click', 'element_label': 'Search', 'api_call_triggered': '/api/guests/search', 'api_method': 'POST', 'api_response_status': 200},
            ]}],
        },
        {
            'journey_title': 'Family & Friends List',
            'outcome': 'blocked',
            'outcome_detail': 'Accept invite requires human input',
            'steps': [{'interactions': [
                {'action': 'click', 'element_label': 'Received Invites Tab'},
                {'action': 'click', 'element_label': 'Accept Invite'},
            ]}],
        },
    ]

    diagram = journeys_to_mermaid(journeys, 'Profile Settings')

    assert diagram.startswith('flowchart TD')
    assert 'A["Start"]' in diagram
    assert 'B["Profile Settings"]' in diagram
    assert diagram.count('["Family and Friends List"]') == 1
    assert '["Add Guest"]' in diagram
    assert '["Enter Guest Details"]' in diagram
    assert '["API POST: /api/guests/search (200)"]' in diagram
    assert '["Completed"]' in diagram
    assert '["Human Input Required"]' in diagram


def test_consolidated_mermaid_is_deterministic():
    journeys = [{
        'journey_title': 'Account Settings',
        'outcome': 'completed',
        'steps': [{'interactions': [
            {'action': 'select', 'element_label': 'Language Preference', 'value': 'French'},
        ]}],
    }]

    first = journeys_to_mermaid(journeys, 'Profile Settings')
    second = journeys_to_mermaid(journeys, 'Profile Settings')

    assert first == second
    assert '["Select French"]' in first
