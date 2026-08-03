from __future__ import annotations

from typing import Any
from uuid import uuid4

from schemas.user_story_schema import AcceptanceCriterion, Story, StoryBundle
from services.agent_prompts import JIRA_AGENT_PROMPT
from services.llm_generation_service import LLMGenerationError, generate_json_with_openai, get_llm_runtime_config


USER_STORY_RESPONSE_CONTRACT = """
Return JSON only in this shape:
{
  "stories": [
    {
      "story_id": "optional; may be blank",
      "journey_id": "must match the source journey_id",
      "epic": "business epic name derived from the journey objective and module",
      "module": "functional module name derived from the real pages and controls",
      "summary": "US-XX concise Jira summary using the actual journey title or goal",
      "description": "As a user, I want ... so that ... Include the actual journey objective, source URL, observed path, and key UI actions.",
      "acceptance_criteria": [
        {"ac_type": "functional", "ac_text": "specific observable behavior from the captured journey", "ac_id": "optional"},
        {"ac_type": "ui", "ac_text": "specific UI behavior, selector, validation, or state from captured evidence", "ac_id": "optional"}
      ],
      "labels": ["short", "lowercase", "tags"],
      "component": "Browser Agent"
    }
  ]
}
Rules:
- Generate one consolidated, high-quality story per journey unless the journey contains clearly separate business outcomes.
- Preserve each journey_id exactly.
- Treat the captured journey objective as authoritative. Use only facts from that journey map: objective, URLs, page titles, steps, events, clicked elements, selectors, input values, validations, screenshots, network statuses, and outcomes.
- Do not invent authentication, roles, APIs, backend systems, pages, or controls unless present in evidence.
- Do not return generic text such as "the application" when real source URL, title, or controls are available.
- Acceptance criteria must be practical, testable, and specific to the captured journey.
"""

_GENERIC_PHRASES = (
    'the application to be converted',
    'the discovered journey for the application',
    'real navigation path',
    'derive automation assets',
    'the business journey is reliable',
)


def _as_text(value: Any, default: str = '') -> str:
    if value is None:
        return default
    return str(value).strip() or default


def _get_first_heading(journey: dict) -> str:
    for step in journey.get('steps', []):
        meta = step.get('metadata') or {}
        title = meta.get('title') or step.get('page_title') or step.get('page')
        if title:
            return str(title)
    return journey.get('source_url', journey.get('application_url', 'Journey'))


def _journey_objective(journey: dict) -> str:
    hints = journey.get('test_hints') or {}
    metadata = journey.get('exploration_metadata') or {}
    return _as_text(hints.get('journey_objective') or metadata.get('task_input'))


def _source_url(journey: dict) -> str:
    return _as_text(journey.get('source_url') or journey.get('starting_url') or journey.get('application_url') or journey.get('app_url'), 'the captured source URL')


def _extract_interactions(journey: dict) -> list[dict[str, Any]]:
    interactions: list[dict[str, Any]] = []
    for step in journey.get('steps') or []:
        page_title = step.get('page_title') or step.get('page') or journey.get('journey_title') or ''
        page_url = step.get('page_url') or step.get('url') or journey.get('starting_url') or journey.get('source_url') or ''
        for interaction in step.get('interactions') or []:
            item = dict(interaction)
            item.setdefault('page_title', page_title)
            item.setdefault('page_url', page_url)
            interactions.append(item)
    if not interactions:
        for event in journey.get('events') or []:
            interactions.append({
                'action': event.get('action') or event.get('event') or 'observe',
                'element_label': event.get('description') or event.get('page') or '',
                'resulted_in': event.get('event') or event.get('description') or '',
                'page_title': event.get('page') or '',
                'page_url': event.get('url') or '',
                'selector': (event.get('metadata') or {}).get('selector') or '',
            })
    return interactions


def _step_titles(journey: dict) -> list[str]:
    titles: list[str] = []
    for step in journey.get('steps') or []:
        title = _as_text(step.get('page_title') or step.get('page') or step.get('name'))
        url = _as_text(step.get('page_url') or step.get('url'))
        if title and url:
            titles.append(f'{title} ({url})')
        elif title:
            titles.append(title)
        elif url:
            titles.append(url)
    if not titles:
        first = _get_first_heading(journey)
        if first:
            titles.append(first)
    return titles


def _interaction_labels(journey: dict, limit: int = 8) -> list[str]:
    labels: list[str] = []
    for interaction in _extract_interactions(journey):
        label = _as_text(interaction.get('element_label') or interaction.get('text') or interaction.get('name') or interaction.get('selector') or interaction.get('action'))
        action = _as_text(interaction.get('action'))
        result = _as_text(interaction.get('resulted_in') or interaction.get('event') or interaction.get('result'))
        parts = [part for part in (action, label, result) if part]
        if parts:
            labels.append(' - '.join(parts))
    deduped = list(dict.fromkeys(labels))
    return deduped[:limit]


def _selector_examples(journey: dict, limit: int = 4) -> list[str]:
    selectors: list[str] = []
    for interaction in _extract_interactions(journey):
        selector = _as_text(interaction.get('selector') or interaction.get('css_selector') or interaction.get('element_id') or interaction.get('role'))
        if selector:
            selectors.append(selector)
    return list(dict.fromkeys(selectors))[:limit]


def _validation_examples(journey: dict, limit: int = 3) -> list[str]:
    validations: list[str] = []
    for interaction in _extract_interactions(journey):
        validation = _as_text(interaction.get('validation_message') or interaction.get('error_message'))
        if validation:
            validations.append(validation)
    return list(dict.fromkeys(validations))[:limit]


def _journey_path_sentence(journey: dict) -> str:
    titles = _step_titles(journey)[:6]
    return ' -> '.join(titles) if titles else _source_url(journey)


def _derive_module(journey: dict) -> str:
    source = _source_url(journey)
    page = _get_first_heading(journey)
    text = (source + ' ' + page + ' ' + _journey_objective(journey) + ' ' + ' '.join(_interaction_labels(journey))).lower()
    if 'checkout' in text or 'cart' in text or 'ticket' in text:
        return 'Checkout and Purchase Journey'
    if 'guest' in text or 'profile' in text:
        return 'Guest Management Journey'
    if 'search' in text or 'lookup' in text or 'report' in text:
        return 'Search and Discovery Journey'
    if 'workspace' in text or 'preferences' in text:
        return 'Workspace Configuration Journey'
    return 'Core Web Journey'


def _derive_epic(journey: dict) -> str:
    return f'{_derive_module(journey)} Epic'


def _derive_labels(journey: dict) -> list[str]:
    labels = ['journey', 'browser', 'qa', 'automation']
    text = (_source_url(journey) + ' ' + _journey_objective(journey) + ' ' + ' '.join(_interaction_labels(journey))).lower()
    for keyword in ('checkout', 'login', 'search', 'report', 'workspace', 'preferences', 'ticket', 'guest', 'navigation', 'form'):
        if keyword in text:
            labels.append(keyword)
    return sorted(set(labels))


def _build_story_summary(journey: dict, index: int) -> str:
    objective = _journey_objective(journey)
    title = journey.get('journey_title') or _get_first_heading(journey) or _source_url(journey)
    if objective:
        words = objective.replace('\n', ' ').split()
        concise = ' '.join(words[:14])
        return f'US-{index:02d} {concise}'[:160]
    return f'US-{index:02d} {title}'[:160]


def _build_story_description(journey: dict) -> str:
    objective = _journey_objective(journey)
    source = _source_url(journey)
    path = _journey_path_sentence(journey)
    actions = _interaction_labels(journey, limit=6)
    outcome = _as_text(journey.get('outcome_detail') or journey.get('outcome'), 'the journey completes with the captured browser outcome')
    capability = objective or f'navigate the captured journey starting from {source}'
    action_text = '; '.join(actions) if actions else 'page load and visible UI inspection were captured'
    return (
        f'As a user, I want to {capability} so that QA can validate the exact journey captured from {source}. '
        f'Captured path: {path}. '
        f'Observed interactions: {action_text}. '
        f'Expected outcome: {outcome}.'
    )


def _build_acceptance_criteria(journey: dict) -> list[AcceptanceCriterion]:
    source = _source_url(journey)
    path = _journey_path_sentence(journey)
    actions = _interaction_labels(journey, limit=8)
    selectors = _selector_examples(journey)
    validations = _validation_examples(journey)
    event_count = len(journey.get('events') or [])
    step_count = len(journey.get('steps') or [])
    outcome = _as_text(journey.get('outcome_detail') or journey.get('outcome'), 'the captured outcome should be reached')
    action_text = '; '.join(actions) if actions else 'the captured page load and inspection events'
    selector_text = ', '.join(selectors) if selectors else 'available stable labels, roles, or selectors'
    validation_text = '; '.join(validations) if validations else 'any observed validation or empty-state messages'

    return [
        AcceptanceCriterion(ac_type='functional', ac_text=f'Given the user starts from {source}, when the captured journey is replayed, then the flow should follow this observed path without introducing unrelated pages: {path}.'),
        AcceptanceCriterion(ac_type='functional', ac_text=f'Given the journey objective is executed, when the user performs the captured actions ({action_text}), then each navigation or same-page state change should be recorded and the final outcome should match: {outcome}.'),
        AcceptanceCriterion(ac_type='ui', ac_text=f'Given the journey contains {step_count} captured step(s) and {event_count} event(s), then each step should expose page title, URL, action, element label, selector or role, result, timestamp, depth, and before or after state where available.'),
        AcceptanceCriterion(ac_type='ui', ac_text=f'Given downstream QA uses this story for automation, then selectors and UI references such as {selector_text} plus validations such as {validation_text} should remain traceable to the original journey map and UI element extraction.'),
    ]


def _is_generic_description(description: str, journey: dict) -> bool:
    lower = description.lower()
    source = _source_url(journey).lower()
    title = _get_first_heading(journey).lower()
    has_evidence = (source and source in lower) or (title and title in lower)
    return not has_evidence or any(phrase in lower for phrase in _GENERIC_PHRASES)


def _deterministic_user_stories(journeys: list[dict], warning: str = '') -> StoryBundle:
    stories: list[Story] = []
    for index, journey in enumerate(journeys, start=1):
        stories.append(
            Story(
                story_id=str(uuid4()),
                journey_id=str(journey.get('journey_id', '')),
                generation_source='fallback',
                generation_model='',
                epic=_derive_epic(journey),
                module=_derive_module(journey),
                summary=_build_story_summary(journey, index),
                description=_build_story_description(journey),
                acceptance_criteria=_build_acceptance_criteria(journey),
                labels=_derive_labels(journey),
                component='Browser Agent',
            )
        )
    return StoryBundle(stories=stories, generation_source='fallback', generation_model='', generation_warning=warning)

def _normalise_story(raw: dict[str, Any], journey: dict[str, Any], index: int) -> Story:
    criteria = raw.get('acceptance_criteria') or []
    normalised_criteria: list[AcceptanceCriterion] = []
    for ac_index, item in enumerate(criteria[:8], start=1):
        if isinstance(item, str):
            normalised_criteria.append(AcceptanceCriterion(ac_type='functional', ac_text=item, ac_id=f'AC-{index:02d}-{ac_index:02d}'))
        elif isinstance(item, dict) and item.get('ac_text'):
            normalised_criteria.append(AcceptanceCriterion(ac_type=str(item.get('ac_type') or 'functional'), ac_text=str(item['ac_text']), ac_id=str(item.get('ac_id') or f'AC-{index:02d}-{ac_index:02d}')))

    evidence_criteria = _build_acceptance_criteria(journey)
    if len(normalised_criteria) < 4:
        normalised_criteria.extend(evidence_criteria[: 4 - len(normalised_criteria)])
    if not any(_source_url(journey) in criterion.ac_text or _get_first_heading(journey) in criterion.ac_text for criterion in normalised_criteria):
        normalised_criteria = evidence_criteria

    description = str(raw.get('description') or '')
    if _is_generic_description(description, journey):
        description = _build_story_description(journey)

    labels = raw.get('labels') if isinstance(raw.get('labels'), list) else _derive_labels(journey)
    runtime = get_llm_runtime_config()
    return Story(
        story_id=str(raw.get('story_id') or uuid4()),
        journey_id=str(journey.get('journey_id') or raw.get('journey_id') or ''),
        generation_source=str(raw.get('generation_source') or 'openai'),
        generation_model=str(raw.get('generation_model') or runtime.model),
        epic=str(raw.get('epic') or _derive_epic(journey)),
        module=str(raw.get('module') or _derive_module(journey)),
        summary=str(raw.get('summary') or _build_story_summary(journey, index))[:160],
        description=description,
        acceptance_criteria=normalised_criteria[:8],
        labels=sorted({str(label).strip().lower().replace(' ', '-') for label in labels if str(label).strip()}),
        component=str(raw.get('component') or 'Browser Agent'),
    )


def _llm_user_stories(journeys: list[dict]) -> StoryBundle:
    payload = {
        'journeys': journeys,
        'evidence_summaries': [
            {
                'journey_id': journey.get('journey_id'),
                'source_url': _source_url(journey),
                'objective': _journey_objective(journey),
                'path': _journey_path_sentence(journey),
                'observed_interactions': _interaction_labels(journey),
                'selectors': _selector_examples(journey),
                'validations': _validation_examples(journey),
                'outcome': journey.get('outcome_detail') or journey.get('outcome'),
            }
            for journey in journeys
        ],
        'generation_guidance': 'Treat the journey objective as authoritative. Create one evidence-grounded Jira story for the captured business outcome, preserve the journey ID, and omit any role, rule, validation, or path not present in the evidence.',
    }
    data = generate_json_with_openai(JIRA_AGENT_PROMPT, payload, response_contract=USER_STORY_RESPONSE_CONTRACT)
    raw_stories = data.get('stories') or []
    if not isinstance(raw_stories, list) or not raw_stories:
        raise LLMGenerationError('OpenAI did not return any user stories.')
    journey_by_id = {str(j.get('journey_id') or ''): j for j in journeys}
    fallback_journey = journeys[0] if journeys else {}
    stories = []
    for index, raw in enumerate(raw_stories, start=1):
        if not isinstance(raw, dict):
            continue
        journey = journey_by_id.get(str(raw.get('journey_id') or '')) or fallback_journey
        stories.append(_normalise_story(raw, journey, index))
    if not stories:
        raise LLMGenerationError('OpenAI returned no valid user story objects.')
    runtime = get_llm_runtime_config()
    return StoryBundle(stories=stories, generation_source='openai', generation_model=runtime.model, generation_warning='')


def enrich_story_for_jira(story: dict[str, Any], journey: dict[str, Any] | None) -> dict[str, Any]:
    """Ensure Jira sync never uploads a generic story when journey evidence exists."""
    if not journey:
        return story
    enriched = dict(story)
    if _is_generic_description(str(enriched.get('description') or ''), journey):
        enriched['description'] = _build_story_description(journey)
    criteria = enriched.get('acceptance_criteria') or []
    criteria_text = ' '.join(str(item.get('ac_text') if isinstance(item, dict) else item) for item in criteria)
    if _source_url(journey) not in criteria_text and _get_first_heading(journey) not in criteria_text:
        enriched['acceptance_criteria'] = [criterion.model_dump() for criterion in _build_acceptance_criteria(journey)]
    if not enriched.get('summary') or 'application' in str(enriched.get('summary')).lower():
        enriched['summary'] = _build_story_summary(journey, 1)
    enriched['epic'] = enriched.get('epic') or _derive_epic(journey)
    enriched['module'] = enriched.get('module') or _derive_module(journey)
    enriched['labels'] = sorted(set((enriched.get('labels') or []) + _derive_labels(journey)))
    return enriched
def generate_user_stories(journeys: list[dict]) -> StoryBundle:
    try:
        return _llm_user_stories(journeys)
    except Exception as exc:
        warning = str(exc) or exc.__class__.__name__
        return _deterministic_user_stories(journeys, warning=warning)