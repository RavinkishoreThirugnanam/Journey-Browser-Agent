from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from services.artifact_file_service import write_json_file
from services.jira_agent_service import generate_user_stories


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


async def run_user_story_pipeline(
    journeys_payload: dict[str, Any] | list[dict[str, Any]],
    output_dir: Path,
    timestamp: str,
) -> dict[str, Any]:
    journeys = _extract_journeys(journeys_payload)
    bundle = generate_user_stories(journeys)
    stories = [story.model_dump() for story in bundle.stories]
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"user_stories_{timestamp}.json"
    write_json_file(output_path.name, {
        "journeys": journeys,
        "stories": stories,
        "count": len(stories),
    })
    return {
        "output_payload": {
            "journeys": journeys,
            "stories": stories,
            "count": len(stories),
        },
        "stories": stories,
        "path": str(output_path),
        "count": len(stories),
    }
