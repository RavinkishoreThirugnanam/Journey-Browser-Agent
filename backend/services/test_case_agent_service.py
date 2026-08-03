from __future__ import annotations

from datetime import date
from typing import Any
from uuid import uuid4

from schemas.test_case_schema import TestCase
from services.agent_prompts import TEST_CASE_AGENT_PROMPT
from services.llm_generation_service import LLMGenerationError, generate_json_with_openai


TEST_CASE_RESPONSE_CONTRACT = """
Return JSON only in this shape:
{
  "items": [
    {
      "test_case_id": "optional; may be blank",
      "title": "Validate ...",
      "description": "professional QA objective",
      "preconditions": ["precondition"],
      "steps": ["clear executable manual step"],
      "expected_results": ["observable expected result"],
      "journey_id": "source journey id",
      "user_story_id": "source story id",
      "user_story": "story summary or description",
      "journey_objective": "source objective",
      "source_evidence": [{"event_id": "source event id", "page_id": "source page id", "url": "observed URL", "action": "observed action", "element": "observed label", "selector": "observed selector", "result": "observed result"}],
      "automation_steps": [{"action": "click|fill|open|inspect", "label": "element label", "selector": "stable selector", "value": "optional", "url": "page url", "destination_url": "optional"}],
      "detailed_steps": [
        {
          "step_number": "1",
          "iframe_context": null,
          "field": "element label",
          "value": null,
          "options": null,
          "description": "detailed step",
          "test_step_description": "automation-friendly step",
          "action": "click|fill|open|inspect",
          "expected_result": "observable result",
          "attributes": {"element_type": "", "element_label": "", "selector": "", "role": "", "resulted_in": ""},
          "extracted_ui_elements_attributes": {"page_url": "", "visible": true, "coordinates": {}, "playwright_locator": ""}
        }
      ],
      "test_data": {"page_url": "", "journey_objective": ""},
      "postconditions": ["postcondition"],
      "test_case_type": "Functional",
      "scenario_type": "Positive|Negative|Edge",
      "priority": "High|Medium|Low",
      "environment": "latest",
      "component": "Browser Agent",
      "epic": "source epic",
      "module": "source module",
      "labels": ["short", "lowercase", "tags"],
      "dependencies": [],
      "covered_acceptance_criteria": []
    }
  ]
}
Rules:
- Generate test cases only for the provided selected user stories.
- Use the selected journey objective and captured evidence as the source of truth. The objective must not be rewritten, broadened, or replaced.
- Include one primary positive case and any meaningful negative or edge case when supported by observed UI controls or validation evidence.
- Preserve journey_id and user_story_id exactly.
- Every step must be traceable to source evidence, selectors, labels, page titles, URLs, validations, or journey objective.
- Do not invent unavailable controls or expected API behavior.
- Produce cases suitable for JSON export and downstream Gherkin/JavaScript generation.
"""

def _journey_lookup(journeys: list[dict]) -> dict[str, dict]:
    return {str(journey.get("journey_id", "")): journey for journey in journeys}


def _objective(journey: dict, story: dict) -> str:
    hints = journey.get("test_hints") or {}
    metadata = journey.get("exploration_metadata") or {}
    return str(hints.get("journey_objective") or hints.get("objective") or metadata.get("task_input") or story.get("objective") or story.get("description") or "Validate the selected user journey").strip()


def _selector(interaction: dict) -> str:
    return str(interaction.get("selector") or interaction.get("css_selector") or interaction.get("element_id") or "").strip()


def _evidence(journey: dict) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for step_index, step in enumerate(journey.get("steps") or [], 1):
        if not isinstance(step, dict):
            continue
        interactions = step.get("interactions") or []
        if not interactions:
            interactions = [{"action": step.get("action", "inspect"), "element_label": step.get("page_title", "page")}]
        for interaction in interactions:
            if not isinstance(interaction, dict):
                continue
            evidence.append({
                "event_id": interaction.get("event_id") or "",
                "page_id": interaction.get("page_id") or "",
                "sequence": interaction.get("sequence_id") or interaction.get("interaction_number") or len(evidence) + 1,
                "step": step_index,
                "page": step.get("page_title") or step.get("page_name") or "Page",
                "url": step.get("page_url") or journey.get("starting_url") or journey.get("application_url", ""),
                "action": str(interaction.get("action") or interaction.get("event") or "inspect").lower(),
                "element": interaction.get("element_label") or interaction.get("element_text") or interaction.get("element_type") or "page",
                "element_type": interaction.get("element_type", ""),
                "selector": _selector(interaction),
                "role": interaction.get("role", ""),
                "value": interaction.get("input_value") or interaction.get("value") or "",
                "destination_url": interaction.get("destination_url") or interaction.get("target_url") or "",
                "result": interaction.get("resulted_in") or interaction.get("result") or "observed",
                "validation_message": interaction.get("validation_message") or "",
                "coordinates": interaction.get("coordinates") or {},
                "visible": interaction.get("visible", interaction.get("is_visible", True)),
            })
    if not evidence:
        evidence.append({"sequence": 1, "step": 1, "page": journey.get("journey_title", "Application"), "url": journey.get("starting_url", ""), "action": "open", "element": "application", "element_type": "page", "selector": "", "role": "", "value": "", "destination_url": "", "result": "page_loaded", "validation_message": "", "coordinates": {}, "visible": True})
    return evidence


def build_source_evidence(journey: dict) -> list[dict[str, Any]]:
    """Return normalized, traceable observations captured for a journey."""
    return _evidence(journey)


def _step_text(item: dict[str, Any]) -> str:
    label = str(item.get("element") or "element").strip()
    selector = str(item.get("selector") or "").strip()
    target = f" using {selector}" if selector else ""
    action = item.get("action", "inspect")
    if action in {"fill", "type", "input"}:
        return f"Fill {label}{target} with the captured test value"
    if action in {"click", "tap", "select", "submit"}:
        return f"Activate {label}{target}"
    if action in {"navigate", "open"}:
        return f"Open {item.get('destination_url') or item.get('url') or label}"
    return f"Inspect {label}{target}"


def _detailed_step(item: dict[str, Any], number: int) -> dict[str, Any]:
    action = item.get("action", "inspect")
    label = item.get("element", "element")
    return {
        "step_number": str(number), "iframe_context": None, "field": label,
        "value": item.get("value") or None, "options": None,
        "description": _step_text(item), "test_step_description": _step_text(item),
        "action": action, "expected_result": item.get("result") or "The interaction completes successfully.",
        "attributes": {"element_type": item.get("element_type", ""), "element_label": label, "selector": item.get("selector", ""), "role": item.get("role", ""), "resulted_in": item.get("result", "")},
        "extracted_ui_elements_attributes": {"page_url": item.get("url", ""), "visible": item.get("visible", True), "coordinates": item.get("coordinates", {}), "playwright_locator": item.get("selector", "")},
    }


def _deterministic_test_cases(journeys: list[dict], stories: list[dict]) -> list[TestCase]:
    """Create professional, traceable cases from selected stories and browser evidence."""
    result: list[TestCase] = []
    journeys_by_id = _journey_lookup(journeys)
    for story in stories:
        journey_id = str(story.get("journey_id") or story.get("source_journey_id") or "")
        journey = journeys_by_id.get(journey_id) or story.get("original_journey") or {}
        summary = str(story.get("summary") or story.get("title") or "Selected user story").strip()
        objective = _objective(journey, story)
        evidence = _evidence(journey)
        detailed_steps = [_detailed_step(item, index) for index, item in enumerate(evidence, 1)]
        steps = [_step_text(item) for item in evidence]
        expected = []
        for item in evidence:
            if item.get("destination_url"):
                expected.append(f"The browser reaches {item['destination_url']}")
            if item.get("validation_message"):
                expected.append(f"The validation result is visible: {item['validation_message']}")
        expected.append(str(journey.get("outcome_detail") or journey.get("outcome") or f"The objective is completed: {objective}"))
        expected = list(dict.fromkeys(expected))
        story_criteria = story.get("acceptance_criteria") or []
        criteria = [item.model_dump() if hasattr(item, "model_dump") else item for item in story_criteria]
        story_code = str(story.get("story_id") or "US").replace(" ", "-")
        test_id = str(uuid4())
        result.append(TestCase(
            test_case_id=test_id, title=f"Validate {summary}", user_story=str(story.get("description") or story.get("summary") or summary),
            description=f"Validate the objective '{objective}' for the journey '{journey.get('journey_title') or journey_id}'. This case is derived from {len(evidence)} observed browser interactions.",
            preconditions=["User has access to the target workflow", f"The application is available at {journey.get('starting_url') or journey.get('application_url') or journey.get('source_url', '')}", f"The journey objective is: {objective}"],
            steps=steps, expected_results=expected, journey_id=journey_id, user_story_id=str(story.get("story_id") or summary),
            journey_objective=objective, source_evidence=evidence, detailed_steps=detailed_steps,
            automation_steps=[{"action": item["action"], "label": item["element"], "selector": item["selector"], "value": item["value"], "url": item["url"], "destination_url": item["destination_url"]} for item in evidence],
            test_data={"page_url": journey.get("starting_url") or journey.get("application_url") or journey.get("source_url", ""), "journey_objective": objective},
            postconditions=expected, test_case_type="Functional", scenario_type="Positive", priority="High", environment="latest",
            component=story.get("component", "Browser Agent"), epic=story.get("epic", "Journey Automation"), module=story.get("module", "Discovered Journey"), labels=story.get("labels", []),
            dependencies=[], covered_acceptance_criteria=criteria, actual_results="",
        ))
    return result

def _normalise_case(raw: dict[str, Any], story: dict[str, Any], journey: dict[str, Any]) -> TestCase:
    raw_evidence = raw.get("source_evidence")
    evidence = [item for item in raw_evidence if isinstance(item, dict)] if isinstance(raw_evidence, list) else []
    if not evidence:
        evidence = _evidence(journey)
    detailed_steps = raw.get("detailed_steps") if isinstance(raw.get("detailed_steps"), list) else [_detailed_step(item, index) for index, item in enumerate(evidence, 1)]
    steps = raw.get("steps") if isinstance(raw.get("steps"), list) and raw.get("steps") else [_step_text(item) for item in evidence]
    expected_results = raw.get("expected_results") if isinstance(raw.get("expected_results"), list) and raw.get("expected_results") else [str(journey.get("outcome_detail") or journey.get("outcome") or "The journey objective is validated successfully.")]
    journey_id = str(story.get("journey_id") or story.get("source_journey_id") or journey.get("journey_id") or raw.get("journey_id") or "")
    user_story_id = str(story.get("story_id") or story.get("summary") or raw.get("user_story_id") or "")
    automation_steps = raw.get("automation_steps") if isinstance(raw.get("automation_steps"), list) else [
        {"action": item.get("action", "inspect"), "label": item.get("element", "element"), "selector": item.get("selector", ""), "value": item.get("value", ""), "url": item.get("url", ""), "destination_url": item.get("destination_url", "")}
        for item in evidence
    ]
    labels = raw.get("labels") if isinstance(raw.get("labels"), list) else story.get("labels", [])
    return TestCase(
        test_case_id=str(raw.get("test_case_id") or uuid4()),
        title=str(raw.get("title") or raw.get("test_case_title") or f"Validate {story.get('summary') or 'selected user story'}"),
        description=str(raw.get("description") or raw.get("test_case_description") or f"Validate the selected user story using captured browser evidence for journey {journey_id}."),
        preconditions=[str(item) for item in (raw.get("preconditions") or ["User has access to the target workflow"])],
        steps=[str(item) for item in steps],
        expected_results=[str(item) for item in expected_results],
        journey_id=journey_id,
        user_story_id=user_story_id,
        user_story=str(raw.get("user_story") or story.get("description") or story.get("summary") or ""),
        journey_objective=_objective(journey, story),
        source_evidence=[item for item in evidence if isinstance(item, dict)],
        automation_steps=[item for item in automation_steps if isinstance(item, dict)],
        detailed_steps=[item for item in detailed_steps if isinstance(item, dict)],
        test_data=raw.get("test_data") if isinstance(raw.get("test_data"), dict) else {"page_url": journey.get("starting_url") or journey.get("source_url") or "", "journey_objective": _objective(journey, story)},
        postconditions=[str(item) for item in (raw.get("postconditions") or expected_results)],
        test_case_type=str(raw.get("test_case_type") or "Functional"),
        scenario_type=str(raw.get("scenario_type") or "Positive"),
        priority=str(raw.get("priority") or "High"),
        environment=str(raw.get("environment") or "latest"),
        component=str(raw.get("component") or story.get("component") or "Browser Agent"),
        epic=str(raw.get("epic") or story.get("epic") or "Journey Automation"),
        module=str(raw.get("module") or story.get("module") or "Discovered Journey"),
        labels=sorted({str(label).strip().lower().replace(" ", "-") for label in labels if str(label).strip()}),
        dependencies=[str(item) for item in (raw.get("dependencies") or [])],
        covered_acceptance_criteria=[item for item in (raw.get("covered_acceptance_criteria") or story.get("acceptance_criteria") or []) if isinstance(item, dict)],
        actual_results=str(raw.get("actual_results") or ""),
    )


def _llm_test_cases(journeys: list[dict], stories: list[dict]) -> list[TestCase]:
    journeys_by_id = _journey_lookup(journeys)
    enriched_stories = []
    for story in stories:
        journey_id = str(story.get("journey_id") or story.get("source_journey_id") or "")
        journey = journeys_by_id.get(journey_id) or story.get("original_journey") or {}
        enriched_stories.append({**story, "source_journey": journey, "source_evidence": _evidence(journey)})
    data = generate_json_with_openai(
        TEST_CASE_AGENT_PROMPT,
        {"journeys": journeys, "stories": enriched_stories, "generation_guidance": "Treat each selected journey objective as authoritative. Generate only evidence-supported cases, preserve source IDs exactly, attach source event/page evidence, and omit unsupported negative or edge scenarios."},
        response_contract=TEST_CASE_RESPONSE_CONTRACT,
    )
    raw_items = data.get("items") or data.get("test_cases") or []
    if not isinstance(raw_items, list) or not raw_items:
        raise LLMGenerationError("OpenAI did not return test cases.")
    story_lookup = {str(story.get("story_id") or story.get("summary") or ""): story for story in stories}
    fallback_story = stories[0] if stories else {}
    cases: list[TestCase] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        story = story_lookup.get(str(raw.get("user_story_id") or "")) or fallback_story
        journey_id = str(raw.get("journey_id") or story.get("journey_id") or story.get("source_journey_id") or "")
        journey = journeys_by_id.get(journey_id) or story.get("original_journey") or {}
        cases.append(_normalise_case(raw, story, journey))
    if not cases:
        raise LLMGenerationError("OpenAI returned no valid test case objects.")
    return cases


def generate_test_cases(journeys: list[dict], stories: list[dict]) -> list[TestCase]:
    try:
        return _llm_test_cases(journeys, stories)
    except Exception:
        return _deterministic_test_cases(journeys, stories)