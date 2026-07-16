from __future__ import annotations

from pathlib import Path
from typing import Any

from services.artifact_file_service import write_json_file
from services.test_case_agent_service import generate_test_cases


def _extract_journeys(payload: dict[str, Any] | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    browser_section = payload.get("browser_agent_section", {})
    if isinstance(browser_section, dict):
        browser_data = browser_section.get("browser_agent_data", {})
        if isinstance(browser_data, dict):
            journeys = browser_data.get("journeys", [])
            if isinstance(journeys, list):
                return [item for item in journeys if isinstance(item, dict)]

    journeys = payload.get("journeys", [])
    if isinstance(journeys, list):
        return [item for item in journeys if isinstance(item, dict)]
    return []


def _extract_stories(payload: dict[str, Any] | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    stories = payload.get("stories", [])
    if isinstance(stories, list):
        return [item for item in stories if isinstance(item, dict)]

    if payload.get("output_payload"):
        nested = payload.get("output_payload", {})
        if isinstance(nested, dict):
            stories = nested.get("stories", [])
            if isinstance(stories, list):
                return [item for item in stories if isinstance(item, dict)]

    journeys = payload.get("journeys", [])
    if isinstance(journeys, list):
        collected: list[dict[str, Any]] = []
        for journey in journeys:
            if not isinstance(journey, dict):
                continue
            generated = journey.get("generated_output", {})
            if isinstance(generated, dict):
                story_list = generated.get("user_stories", [])
                if isinstance(story_list, list):
                    collected.extend(item for item in story_list if isinstance(item, dict))
        return collected
    return []


def _build_story_lookup(stories: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for story in stories:
        for key in (story.get("story_id"), story.get("us_id"), story.get("summary")):
            if key:
                lookup[str(key)] = story
    return lookup


def _attach_story_journey(stories: list[dict[str, Any]], journeys: list[dict[str, Any]]) -> list[dict[str, Any]]:
    journey_map = {str(j.get("journey_id", "")): j for j in journeys if isinstance(j, dict)}
    attached: list[dict[str, Any]] = []
    for story in stories:
        if not isinstance(story, dict):
            continue
        journey_id = str(story.get("journey_id") or story.get("source_journey_id") or "")
        matched_journey = journey_map.get(journey_id)
        if matched_journey:
            attached.append({
                **story,
                "original_journey": matched_journey,
            })
        else:
            attached.append(story)
    return attached


async def run_test_case_pipeline(
    journeys_payload: dict[str, Any] | list[dict[str, Any]],
    stories_payload: dict[str, Any] | list[dict[str, Any]],
    output_dir: Path,
    timestamp: str,
) -> dict[str, Any]:
    journeys = _extract_journeys(journeys_payload)
    stories = _extract_stories(stories_payload)
    stories = _attach_story_journey(stories, journeys)

    results: list[dict[str, Any]] = []
    generated = generate_test_cases(journeys, stories)
    for item in generated:
        results.append(item.model_dump())

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"test_cases_{timestamp}.json"
    write_json_file(output_path.name, {
        "journeys": journeys,
        "stories": stories,
        "items": results,
        "count": len(results),
    })
    return {
        "output_payload": {
            "journeys": journeys,
            "stories": stories,
            "items": results,
            "count": len(results),
        },
        "items": results,
        "path": str(output_path),
        "count": len(results),
    }
