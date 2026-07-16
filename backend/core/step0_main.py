from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from routers.configuration_router import _read as read_configuration
from services.artifact_file_service import unique_filename, write_json_file, write_text_file
from services.browser_agent_service import explore_application
from services.journey_map_service import save_journey
from core.step4_script_agent import run_test_script_pipeline
from core.step2_user_story_agent import run_user_story_pipeline
from core.step3_test_case_agents import run_test_case_pipeline
from core.ui_elements_extractor.main import run_ui_elements_pipeline


logger = logging.getLogger("step0_main")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
GENERATED_DIR = STORAGE_DIR / "generated_files"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _latest_json(path: Path) -> Path | None:
    if not path.exists() or not path.is_dir():
        return None
    files = sorted(path.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _latest_journey_file() -> Path | None:
    if not GENERATED_DIR.exists():
        return None
    candidates = sorted(GENERATED_DIR.glob("journeys*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _load_json(path: str | Path) -> object:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _save_pipeline_summary(payload: dict) -> Path:
    _ensure_dir(GENERATED_DIR)
    filename = unique_filename(f"pipeline_summary_{TIMESTAMP}", ".md")
    content = [
        "# Pipeline Summary",
        "",
        f"- Timestamp: {TIMESTAMP}",
        f"- Journey count: {payload.get('journey_count', 0)}",
        f"- User story count: {payload.get('user_story_count', 0)}",
        f"- Test case count: {payload.get('test_case_count', 0)}",
        f"- Test script count: {payload.get('test_script_count', 0)}",
    ]
    return write_text_file(filename, "\n".join(content))


def _journey_payload_to_path(journey_payload: dict | str | Path | object) -> Path:
    _ensure_dir(GENERATED_DIR)
    if isinstance(journey_payload, Path):
        return journey_payload
    if isinstance(journey_payload, str):
        candidate = Path(journey_payload)
        if candidate.exists():
            return candidate
        loaded = _load_json(journey_payload)
        if isinstance(loaded, dict):
            path = GENERATED_DIR / f"journeys_{TIMESTAMP}.json"
            write_json_file(path.name, loaded)
            return path
    if isinstance(journey_payload, dict):
        path = GENERATED_DIR / f"journeys_{TIMESTAMP}.json"
        write_json_file(path.name, journey_payload)
        return path
    raise TypeError("Unsupported journey payload type for Step 1.5")


def _extract_journeys_from_payload(payload: dict | list | None) -> list[dict]:
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


async def run_step1_browser_agent(application_url: str, parameters: dict[str, str] | None = None, crawl: dict | None = None):
    parameters = parameters or {}
    crawl = crawl or {}
    logger.info("STEP 1: browser agent starting for %s", application_url)
    exploration = explore_application(application_url, parameters, crawl)
    save_journey(exploration)
    logger.info("STEP 1 complete: %s journey(s) discovered", len(exploration.journeys))
    return exploration


async def run_step1_5_ui_elements(journey_payload: dict | str | Path | object | None):
    logger.info("STEP 1.5: UI element enrichment")
    if journey_payload is None:
        input_path = _latest_journey_file()
        if input_path is None:
            raise FileNotFoundError("No journey JSON found for Step 1.5 enrichment")
    else:
        input_path = _journey_payload_to_path(journey_payload)

    combined_path = run_ui_elements_pipeline(str(input_path), site="wdw")
    if not combined_path:
        raise RuntimeError("Step 1.5 completed without producing a combined enrichment file")

    combined_data = _load_json(combined_path) or {}
    logger.info("STEP 1.5 complete: combined output written to %s", combined_path)
    return {
        "combined_path": combined_path,
        "browser_agent_section": combined_data.get("browser_agent_section", {}),
        "page_url_ui_element_section": combined_data.get("page_url_ui_element_section", {}),
    }


async def run_step2_user_story_agent(journeys_payload: dict | list):
    logger.info("STEP 2: user story generation")
    result = await run_user_story_pipeline(journeys_payload, GENERATED_DIR, TIMESTAMP)
    logger.info("STEP 2 complete: %s story(ies) generated", len(result.get("stories", [])))
    return result


async def run_step3_test_case_agent(journeys_payload: dict | list, stories_payload: dict | list):
    logger.info("STEP 3: test case generation")
    result = await run_test_case_pipeline(journeys_payload, stories_payload, GENERATED_DIR, TIMESTAMP)
    logger.info("STEP 3 complete: %s test case(s) generated", len(result.get("items", [])))
    return result


async def run_step4_test_script_agent(test_cases_payload: dict | list):
    logger.info("STEP 4: test script generation")
    result = await run_test_script_pipeline(test_cases_payload, GENERATED_DIR, TIMESTAMP)
    logger.info("STEP 4 complete: %s script(s) generated", len(result.get("items", [])))
    return result


async def run_all(application_url: str | None = None):
    config = read_configuration()
    application = config.get("application", {})
    application_url = application_url or application.get("base_url", "")
    if not application_url:
        raise FileNotFoundError("No application URL provided and no configured base URL found")

    browser_result = await run_step1_browser_agent(application_url, application.get("global_parameters", {}), {"max_depth": 1, "max_pages": 8, "follow_links": True})
    journey_models = [j.model_dump() for j in browser_result.journeys]
    ui_elements_result = await run_step1_5_ui_elements(browser_result.model_dump() if hasattr(browser_result, "model_dump") else {"journeys": journey_models})

    combined_data = {}
    combined_path = ui_elements_result.get("combined_path")
    if combined_path:
        loaded_combined = _load_json(combined_path)
        if isinstance(loaded_combined, dict):
            combined_data = loaded_combined

    journeys = _extract_journeys_from_payload(combined_data) or journey_models
    story_result = await run_step2_user_story_agent(combined_data or {"journeys": journeys})
    story_payload = story_result.get("output_payload") or {}
    story_journeys = _extract_journeys_from_payload(story_payload) or journeys
    story_items = story_result.get("stories", [])
    case_result = await run_step3_test_case_agent(story_payload or {"journeys": story_journeys}, story_payload or {"stories": story_items})
    script_result = await run_step4_test_script_agent(case_result.get("output_payload") or {"items": case_result.get("items", [])})

    summary_path = _save_pipeline_summary({
        "journey_count": len(journeys),
        "user_story_count": len(story_items),
        "test_case_count": len(case_result.get("items", [])),
        "test_script_count": len(script_result["items"]),
    })

    return {
        "journeys": journeys,
        "ui_elements": ui_elements_result.get("page_url_ui_element_section", {}).get("ui_elements_data", []),
        "combined_path": combined_path,
        "user_stories": story_items,
        "test_cases": case_result["items"],
        "test_scripts": script_result["items"],
        "summary_path": str(summary_path),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Step 0 pipeline orchestrator")
    sub = parser.add_subparsers(dest="command", required=True)

    all_cmd = sub.add_parser("all", help="Run the full pipeline")
    all_cmd.add_argument("--application-url", default=None)

    run_cmd = sub.add_parser("run", help="Run a single step")
    run_cmd.add_argument("--step", type=float, choices=[1, 1.5, 2, 3, 4], required=True)
    run_cmd.add_argument("--application-url", default=None)

    return parser


async def main():
    args = build_parser().parse_args()
    if args.command == "all":
        result = await run_all(args.application_url)
        logger.info("Pipeline summary written to %s", result["summary_path"])
        return

    if args.command == "run":
        config = read_configuration()
        application_url = args.application_url or config.get("application", {}).get("base_url", "")
        if args.step == 1:
            await run_step1_browser_agent(application_url, config.get("application", {}).get("global_parameters", {}), {"max_depth": 1, "max_pages": 8, "follow_links": True})
        elif args.step == 1.5:
            await run_step1_5_ui_elements(_latest_journey_file())
        elif args.step == 2:
            await run_step2_user_story_agent(_load_json(_latest_journey_file()) if _latest_journey_file() else {})
        elif args.step == 3:
            await run_step3_test_case_agent(_load_json(_latest_journey_file()) if _latest_journey_file() else {}, {})
        elif args.step == 4:
            raise NotImplementedError("Step 4 requires test cases. Use the full pipeline or wire the input file path next.")


if __name__ == "__main__":
    asyncio.run(main())
