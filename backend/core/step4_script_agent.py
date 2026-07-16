from __future__ import annotations

from pathlib import Path
from typing import Any

from services.artifact_file_service import write_json_file
from services.test_script_agent_service import generate_test_scripts


def _extract_test_cases(payload: dict[str, Any] | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    items = payload.get("items", [])
    if isinstance(items, list) and items:
        return [item for item in items if isinstance(item, dict)]

    test_cases = payload.get("test_cases", [])
    if isinstance(test_cases, list):
        return [item for item in test_cases if isinstance(item, dict)]
    return []


async def run_test_script_pipeline(
    test_cases_payload: dict[str, Any] | list[dict[str, Any]],
    output_dir: Path,
    timestamp: str,
) -> dict[str, Any]:
    test_cases = _extract_test_cases(test_cases_payload)
    scripts = [item.model_dump() for item in generate_test_scripts(test_cases)]

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"test_scripts_{timestamp}.json"
    write_json_file(output_path.name, {
        "test_cases": test_cases,
        "items": scripts,
        "count": len(scripts),
    })
    return {
        "output_payload": {
            "test_cases": test_cases,
            "items": scripts,
            "count": len(scripts),
        },
        "items": scripts,
        "path": str(output_path),
        "count": len(scripts),
    }
