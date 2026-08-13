import json

from core.config import STORAGE_DIR


_ARTIFACT_PATHS = {
    "journeys": STORAGE_DIR / "journeys.json",
    "configurations": STORAGE_DIR / "configurations.json",
    "user-stories": STORAGE_DIR / "user_stories.json",
    "test-cases": STORAGE_DIR / "test_cases.json",
    "test-scripts": STORAGE_DIR / "test_scripts.json",
}


def _journey_preview(items: list) -> list[dict]:
    preview: list[dict] = []
    for bundle in items:
        if not isinstance(bundle, dict):
            continue
        metadata = bundle.get("exploration_metadata") or {}
        journeys = bundle.get("journeys")
        if not isinstance(journeys, list):
            journeys = [bundle]
        for journey in journeys:
            if not isinstance(journey, dict):
                continue
            hints = journey.get("test_hints") or {}
            steps = journey.get("steps") or []
            step_summaries = []
            for step in steps[:25]:
                if not isinstance(step, dict):
                    continue
                interactions = step.get("interactions") or []
                step_summaries.append({
                    "number": step.get("step_number"),
                    "title": step.get("page_title") or step.get("title") or step.get("description") or "Captured page",
                    "url": step.get("page_url") or step.get("url") or step.get("source_url") or "",
                    "action": step.get("action") or step.get("event") or "Observed",
                    "interaction_count": len(interactions) if isinstance(interactions, list) else 0,
                })
            event_ids = hints.get("event_ids") or []
            page_ids = hints.get("page_ids") or []
            event_log = journey.get("event_log") or journey.get("events") or []
            preview.append({
                "id": journey.get("journey_id") or metadata.get("exploration_id") or "",
                "title": journey.get("journey_title") or journey.get("starting_point") or metadata.get("starting_feature") or "Untitled journey",
                "source_url": journey.get("starting_url") or metadata.get("app_url") or "",
                "outcome": journey.get("outcome") or "Captured",
                "captured_at": metadata.get("exploration_timestamp") or journey.get("created_at") or "",
                "objective": hints.get("journey_objective") or metadata.get("task_input") or "",
                "depth": journey.get("total_depth", metadata.get("depth_level", 0)),
                "step_count": len(steps),
                "event_count": len(event_log) if isinstance(event_log, list) and event_log else len(event_ids),
                "page_count": len(set(page_ids)),
                "steps": step_summaries,
            })
    return preview


def _story_preview(items: list) -> list[dict]:
    return [{
        "id": item.get("story_id", ""),
        "journey_id": item.get("journey_id", ""),
        "title": item.get("summary") or "Untitled user story",
        "module": item.get("module") or item.get("epic") or "",
        "description": item.get("description") or "",
        "acceptance_criteria": item.get("acceptance_criteria") or [],
        "status": item.get("jira_sync_status") or "Local",
    } for item in items if isinstance(item, dict)]


def _test_case_preview(items: list) -> list[dict]:
    return [{
        "id": item.get("test_case_id", ""),
        "journey_id": item.get("journey_id", ""),
        "title": item.get("title") or "Untitled test case",
        "description": item.get("description") or "",
        "priority": item.get("priority") or "",
        "type": item.get("test_case_type") or item.get("scenario_type") or "Functional",
        "preconditions": item.get("preconditions") or [],
        "steps": item.get("steps") or [],
        "expected_results": item.get("expected_results") or [],
        "evidence_count": len(item.get("source_evidence") or []),
    } for item in items if isinstance(item, dict)]


def _test_script_preview(items: list) -> list[dict]:
    return [{
        "id": item.get("script_id", ""),
        "test_case_id": item.get("test_case_id", ""),
        "title": item.get("feature_filename") or item.get("javascript_filename") or "Generated test script",
        "feature_filename": item.get("feature_filename") or "",
        "javascript_filename": item.get("javascript_filename") or "",
        "objective": item.get("journey_objective") or "",
        "evidence_count": item.get("source_evidence_count", 0),
        "generated_at": item.get("generated_at") or "",
    } for item in items if isinstance(item, dict)]


def _build_preview(artifact_type: str, items: list) -> list[dict]:
    if artifact_type == "journeys":
        return _journey_preview(items)
    if artifact_type == "user-stories":
        return _story_preview(items)
    if artifact_type == "test-cases":
        return _test_case_preview(items)
    if artifact_type == "test-scripts":
        return _test_script_preview(items)
    return []


def export_artifact(artifact_type: str, preview: bool = False) -> dict:
    path = _ARTIFACT_PATHS.get(artifact_type)
    if not path or not path.exists():
        return {"artifact_type": artifact_type, "items": [], "preview": preview}
    raw = path.read_text(encoding="utf-8")
    items = json.loads(raw) if raw.strip() else []
    if preview:
        preview_items = _build_preview(artifact_type, items)
        return {
            "artifact_type": artifact_type,
            "items": preview_items,
            "count": len(preview_items),
            "preview": True,
        }
    return {"artifact_type": artifact_type, "items": items}