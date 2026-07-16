from uuid import uuid4

from schemas.test_case_schema import TestCase


def _journey_lookup(journeys: list[dict]) -> dict[str, dict]:
    return {journey.get('journey_id', ''): journey for journey in journeys}


def generate_test_cases(journeys: list[dict], stories: list[dict]) -> list[TestCase]:
    """Generate test cases directly from selected user stories.

    Journeys provide context only; each selected story receives its own test case
    so the traceability remains story-first for Jira and review screens.
    """
    result: list[TestCase] = []
    journeys_by_id = _journey_lookup(journeys)

    for story in stories:
        journey_id = story.get('journey_id', '')
        journey = journeys_by_id.get(journey_id, {})
        story_summary = story.get('summary') or story.get('title') or 'Selected user story'
        journey_title = journey.get('journey_title') or journey.get('source_url') or journey.get('application_url') or journey_id or 'selected journey'

        result.append(
            TestCase(
                test_case_id=str(uuid4()),
                title=f"Validate {story_summary}",
                description=f"Verify the acceptance path for user story '{story_summary}' within {journey_title}.",
                preconditions=[
                    'Application is available',
                    'User has access to the target workflow',
                    f"User story is available: {story_summary}",
                ],
                steps=[
                    'Open the application journey entry point',
                    'Execute the journey actions associated with the selected story',
                    'Validate functional outcomes and visible UI feedback',
                    'Confirm the story acceptance criteria are satisfied',
                ],
                expected_results=[
                    'The selected story flow completes successfully',
                    'Expected UI states, validations, and journey outcomes are visible',
                    'No blocking errors occur during the story flow',
                ],
                journey_id=journey_id,
                user_story_id=story.get('story_id') or story_summary,
            )
        )

    return result
