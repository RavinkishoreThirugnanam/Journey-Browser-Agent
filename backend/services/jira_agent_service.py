from __future__ import annotations

from uuid import uuid4

from schemas.user_story_schema import AcceptanceCriterion, Story, StoryBundle


def _get_first_heading(journey: dict) -> str:
    for step in journey.get('steps', []):
        meta = step.get('metadata') or {}
        title = meta.get('title') or step.get('page')
        if title:
            return str(title)
    return journey.get('source_url', journey.get('application_url', 'Journey'))


def _derive_module(journey: dict) -> str:
    source = journey.get('source_url') or journey.get('application_url') or ''
    page = _get_first_heading(journey)
    if 'checkout' in (source + ' ' + page).lower():
        return 'Checkout and Purchase Journey'
    if 'guest' in (source + ' ' + page).lower():
        return 'Guest Management Journey'
    if 'search' in (source + ' ' + page).lower():
        return 'Search and Discovery Journey'
    return 'Core Web Journey'


def _derive_epic(journey: dict) -> str:
    module = _derive_module(journey)
    return f'{module} Epic'


def _derive_labels(journey: dict) -> list[str]:
    labels = ['journey', 'browser', 'qa', 'automation']
    source = (journey.get('source_url') or '').lower()
    if 'checkout' in source:
        labels.append('checkout')
    if 'login' in source or 'sign in' in source:
        labels.append('auth')
    if 'search' in source:
        labels.append('search')
    return sorted(set(labels))


def _build_acceptance_criteria(journey: dict) -> list[AcceptanceCriterion]:
    steps = journey.get('steps', [])
    max_length = 0
    for step in steps:
        metadata = step.get('metadata') or {}
        for key in ('inputs', 'buttons', 'links', 'title'):
            value = metadata.get(key)
            if isinstance(value, str):
                max_length = max(max_length, len(value))
    target_url = journey.get('source_url') or journey.get('application_url') or ''
    page_title = _get_first_heading(journey)
    event_count = len(journey.get('events', []))

    return [
        AcceptanceCriterion(ac_type='functional', ac_text=f'The journey should preserve the original navigation order from {target_url} and allow the user to move through the discovered pages without losing the captured sequence or source URL context.'),
        AcceptanceCriterion(ac_type='functional', ac_text=f'Any discovered CTA, link, or navigation action on {page_title} should resolve to the expected same-origin destination and record the resulting page transition in the journey output across {event_count} captured events.'),
        AcceptanceCriterion(ac_type='ui', ac_text='The journey detail view should display the extracted steps and event log in a readable, scrollable format with page title, action, event, depth, and description visible for review.'),
        AcceptanceCriterion(ac_type='ui', ac_text='The UI should surface the journey summary, step count, and event count clearly, and if any input controls are discovered the detail view should retain their labels and metadata such as max-length or placeholder text when available.' + (f' The longest captured UI text reference is {max_length} characters long.' if max_length else '')),
    ]


def generate_user_stories(journeys: list[dict]) -> StoryBundle:
    stories: list[Story] = []
    for index, journey in enumerate(journeys, start=1):
        journey_title = journey.get('journey_title') or _get_first_heading(journey)
        summary_id = f'US-{index:02d} {journey_title}'[:160]
        description = f"As a user, I want the discovered journey for {journey.get('source_url', journey.get('application_url', 'the application'))} to be converted into a Jira-ready story so that the QA team can validate the flow and derive automation assets from the real navigation path."
        stories.append(
            Story(
                story_id=str(uuid4()),
                journey_id=str(journey.get('journey_id', '')),
                epic=_derive_epic(journey),
                module=_derive_module(journey),
                summary=summary_id,
                description=description,
                acceptance_criteria=_build_acceptance_criteria(journey),
                labels=_derive_labels(journey),
                component='Browser Agent',
            )
        )
    return StoryBundle(stories=stories)
