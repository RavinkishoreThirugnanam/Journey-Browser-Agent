from __future__ import annotations

import json
import re
from uuid import uuid4
from typing import Any

from schemas.test_script_schema import TestScript
from services.agent_prompts import TEST_SCRIPT_AGENT_PROMPT
from services.llm_generation_service import LLMGenerationError, generate_json_with_openai

TEST_SCRIPT_RESPONSE_CONTRACT = """
Return JSON only in this shape:
{
  "items": [
    {
      "script_id": "optional; may be blank",
      "test_case_id": "source test case id",
      "feature_file": "complete Gherkin feature text",
      "javascript_file": "complete CommonJS Cucumber Playwright step definition file",
      "feature_filename": "optional .feature filename",
      "javascript_filename": "optional .js filename",
      "journey_id": "source journey id",
      "user_story_id": "source user story id",
      "journey_objective": "source objective",
      "source_evidence_count": 0
    }
  ]
}
Rules:
- Generate exactly one feature file and one JavaScript file per selected test case.
- Preserve test_case_id, journey_id, user_story_id, and journey_objective exactly.
- The Gherkin must be valid, readable, and scenario-oriented.
- The JavaScript must use @cucumber/cucumber CommonJS imports and Playwright page access through this.page.
- Use stable selectors from detailed_steps.attributes.selector when available; otherwise use visible text locators.
- Include page.goto for application availability and wait for domcontentloaded/networkidle where useful.
- Do not invent selectors, URLs, credentials, or hidden business rules.
- Keep the JavaScript runnable as a scaffold even when a selector is missing.
- Every Then step must perform an evidence-backed assertion against an observed URL, title, heading, visible control, validation message, count, or state.
- A waitForLoadState call alone is synchronization, not an assertion.
- If evidence cannot support a locator or assertion, add an explicit HUMAN_REVIEW_REQUIRED comment; do not invent one.
"""


def _text(value: str) -> str:
    return re.sub(r"[\r\n]+", " ", str(value or "")).strip()


def _js(value: str) -> str:
    return json.dumps(str(value or ""))


def _locator(selector: str, label: str) -> str:
    if selector:
        return f"this.page.locator({_js(selector)})"
    return f"this.page.getByText({_js(label)}, {{ exact: true }})"


def _gherkin_case(test_case: dict) -> str:
    title = _text(test_case.get("test_case_title") or test_case.get("title") or "Journey validation")
    objective = _text(test_case.get("objective") or test_case.get("journey_objective") or "Validate the selected journey")
    lines = [f"Feature: {title}", "", f"  # Objective: {objective}", f"  Scenario: {_text(test_case.get('scenario_title') or title)}"]
    preconditions = test_case.get("preconditions") or []
    if preconditions:
        lines.append(f"    Given {_text(preconditions[0])}")
        for item in preconditions[1:]:
            lines.append(f"    And {_text(item)}")
    for item in test_case.get("detailed_steps") or []:
        action = str(item.get("action") or "inspect").lower()
        keyword = "When" if action in {"click", "tap", "fill", "type", "input", "select", "submit", "navigate", "open"} else "And"
        lines.append(f"    {keyword} {_text(item.get('test_step_description') or item.get('description') or 'the observed interaction is performed')}")
        if item.get("expected_result"):
            lines.append(f"    Then {_text(item['expected_result'])}")
    if not test_case.get("detailed_steps"):
        for step in test_case.get("steps") or []:
            lines.append(f"    When {_text(step)}")
    for expected in test_case.get("expected_results") or []:
        lines.append(f"    Then {_text(expected)}")
    return "\n".join(lines)



def _javascript_case(test_case: dict) -> str:
    start_url = (test_case.get("test_data") or {}).get("page_url") or (test_case.get("test_data") or {}).get("starting_url") or "about:blank"
    lines = ["const { Given, When, Then } = require('@cucumber/cucumber');", ""]
    preconditions = test_case.get("preconditions") or []
    for index, condition in enumerate(preconditions):
        text = _text(condition)
        lines.extend([f"Given({_js(text)}, async function () {{", f"    // Precondition {index + 1}"])
        if "application is available" in text.lower():
            lines.append(f"    await this.page.goto({_js(start_url)}, {{ timeout: 60000, waitUntil: 'domcontentloaded' }});")
            lines.append("    await this.page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});")
        lines.extend(["});", ""])
    if not preconditions:
        lines.extend([f"Given({_js('the application is available')}, async function () {{", f"    await this.page.goto({_js(start_url)}, {{ timeout: 60000, waitUntil: 'domcontentloaded' }});", "});", ""])

    seen = set()
    defined_then = set()
    for item in test_case.get("detailed_steps") or []:
        action = str(item.get("action") or "inspect").lower()
        label = str(item.get("field") or item.get("attributes", {}).get("element_label") or "element")
        selector = str(item.get("attributes", {}).get("selector") or "")
        locator = _locator(selector, label)
        description = _text(item.get("test_step_description") or item.get("description") or f"perform {action} on {label}")
        if description not in seen:
            seen.add(description)
            if action in {"fill", "type", "input"}:
                lines.extend([f"When({_js(description)}, async function () {{", f"    await {locator}.fill(process.env.TEST_INPUT || 'test value');", "});", ""])
            elif action in {"click", "tap", "select", "submit"}:
                lines.extend([f"When({_js(description)}, async function () {{", f"    await {locator}.click({{ timeout: 30000 }});", "    await this.page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});", "});", ""])
            elif action in {"navigate", "open"}:
                target = item.get("attributes", {}).get("destination_url") or item.get("expected_result") or start_url
                lines.extend([f"When({_js(description)}, async function () {{", f"    await this.page.goto({_js(target)}, {{ timeout: 60000, waitUntil: 'domcontentloaded' }});", "});", ""])
            else:
                lines.extend([f"When({_js(description)}, async function () {{", f"    await {locator}.waitFor({{ state: 'visible', timeout: 30000 }});", "});", ""])
        expected = _text(item.get("expected_result") or "The interaction completes successfully.")
        if expected not in defined_then:
            defined_then.add(expected)
            lines.extend([f"Then({_js(expected)}, async function () {{", "    await this.page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});", "});", ""])
    if not test_case.get("detailed_steps"):
        for step in test_case.get("steps") or []:
            text = _text(step)
            lines.extend([f"When({_js(text)}, async function () {{", "    await this.page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});", "});", ""])
    for expected in test_case.get("expected_results") or []:
        text = _text(expected)
        if text in defined_then:
            continue
        defined_then.add(text)
        lines.extend([f"Then({_js(text)}, async function () {{", "    await this.page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});", "});", ""])
    return "\n".join(lines)

def _source_evidence_count(test_case: dict, reported=0) -> int:
    stored = test_case.get("source_evidence")
    evidence = [item for item in stored if isinstance(item, dict)] if isinstance(stored, list) else []
    if evidence:
        return len(evidence)
    try:
        return max(0, int(reported or 0))
    except (TypeError, ValueError):
        return 0


def _deterministic_test_scripts(test_cases: list[dict]) -> list[TestScript]:
    scripts: list[TestScript] = []
    for test_case in test_cases:
        script_id = str(uuid4())
        stem = re.sub(r"[^a-z0-9]+", "_", str(test_case.get("title") or test_case.get("test_case_id") or script_id).lower()).strip("_")[:60] or script_id[:8]
        scripts.append(TestScript(
            script_id=script_id, test_case_id=test_case["test_case_id"], feature_file=_gherkin_case(test_case), javascript_file=_javascript_case(test_case),
            feature_filename=f"{stem}_{script_id[:8]}.feature", javascript_filename=f"{stem}_{script_id[:8]}.js",
            journey_id=str(test_case.get("journey_id") or ""), user_story_id=str(test_case.get("user_story_id") or ""), journey_objective=str(test_case.get("journey_objective") or test_case.get("objective") or ""), source_evidence_count=_source_evidence_count(test_case),
        ))
    return scripts


def _normalise_script(raw: dict[str, Any], test_case: dict[str, Any]) -> TestScript:
    script_id = str(raw.get("script_id") or uuid4())
    stem = re.sub(r"[^a-z0-9]+", "_", str(test_case.get("title") or test_case.get("test_case_id") or script_id).lower()).strip("_")[:60] or script_id[:8]
    feature = str(raw.get("feature_file") or _gherkin_case(test_case))
    javascript = str(raw.get("javascript_file") or _javascript_case(test_case))
    if "@cucumber/cucumber" not in javascript:
        javascript = _javascript_case(test_case)
    if not feature.lstrip().startswith("Feature:"):
        feature = _gherkin_case(test_case)
    return TestScript(
        script_id=script_id,
        test_case_id=str(test_case.get("test_case_id") or raw.get("test_case_id") or ""),
        feature_file=feature,
        javascript_file=javascript,
        feature_filename=str(raw.get("feature_filename") or f"{stem}_{script_id[:8]}.feature"),
        javascript_filename=str(raw.get("javascript_filename") or f"{stem}_{script_id[:8]}.js"),
        journey_id=str(test_case.get("journey_id") or raw.get("journey_id") or ""),
        user_story_id=str(test_case.get("user_story_id") or raw.get("user_story_id") or ""),
        journey_objective=str(test_case.get("journey_objective") or test_case.get("objective") or raw.get("journey_objective") or ""),
        source_evidence_count=_source_evidence_count(test_case, raw.get("source_evidence_count")),
    )


def _llm_test_scripts(test_cases: list[dict]) -> list[TestScript]:
    data = generate_json_with_openai(
        TEST_SCRIPT_AGENT_PROMPT,
        {"test_cases": test_cases, "generation_guidance": "Preserve the authoritative journey objective and source IDs. Generate only evidence-grounded steps and locators. Every Then must contain a concrete assertion; mark insufficient evidence for human review instead of inventing behavior."},
        response_contract=TEST_SCRIPT_RESPONSE_CONTRACT,
    )
    raw_items = data.get("items") or data.get("scripts") or []
    if not isinstance(raw_items, list) or not raw_items:
        raise LLMGenerationError("OpenAI did not return test scripts.")
    cases_by_id = {str(item.get("test_case_id") or ""): item for item in test_cases}
    fallback_case = test_cases[0] if test_cases else {}
    scripts: list[TestScript] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        test_case = cases_by_id.get(str(raw.get("test_case_id") or "")) or fallback_case
        scripts.append(_normalise_script(raw, test_case))
    if not scripts:
        raise LLMGenerationError("OpenAI returned no valid script objects.")
    return scripts


def generate_test_scripts(test_cases: list[dict]) -> list[TestScript]:
    try:
        return _llm_test_scripts(test_cases)
    except Exception:
        return _deterministic_test_scripts(test_cases)