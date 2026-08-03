"""Business assurance analysis derived from captured journey evidence.

This analyzer is read-only. It reports what the current capture can prove and
marks unsupported assurance areas as partial or not assessed.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

CONTROL_ACTIONS = {"click", "hover", "fill", "type", "input", "select", "submit", "tap"}
FAILURE_WORDS = ("failed", "error", "timeout", "blocked", "denied", "not visible", "unavailable")
EXHAUSTIVE_WORDS = ("all ", "every ", "complete ", "entire ", "each ")
SCAN_PATTERN = re.compile(
    r"page scan found\s+(?P<headings>\d+)\s+headings,\s+"
    r"(?P<buttons>\d+)\s+buttons,\s+(?P<links>\d+)\s+links,\s+"
    r"(?P<inputs>\d+)\s+inputs,\s+(?P<menus>\d+)\s+menus,\s+"
    r"(?:and\s+)?(?P<forms>\d+)\s+forms", re.I,
)


def _normalise(value: Any) -> str:
    text = str(value or "").lower().replace("&", " and ")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


def _percentage(numerator: int, denominator: int) -> int | None:
    return None if denominator <= 0 else round(min(100, max(0, numerator * 100 / denominator)))


def _flatten_interactions(journey: dict) -> list[dict]:
    interactions: list[dict] = []
    for step in journey.get("steps") or []:
        if not isinstance(step, dict):
            continue
        page_url = str(step.get("page_url") or journey.get("starting_url") or "")
        page_title = str(step.get("page_title") or journey.get("journey_title") or "")
        for interaction in step.get("interactions") or []:
            if isinstance(interaction, dict):
                interactions.append({**interaction, "_page_url": page_url, "_page_title": page_title})
    return interactions


def _control_key(interaction: dict) -> str:
    page = interaction.get("page_id") or interaction.get("_page_url") or interaction.get("page_url") or ""
    selector = interaction.get("selector") or ""
    label = interaction.get("element_label") or ""
    return _normalise(f"{page}|{selector or label}")


def _page_scan_inventory(interactions: list[dict]) -> dict[str, dict[str, int]]:
    pages: dict[str, dict[str, int]] = {}
    for interaction in interactions:
        match = SCAN_PATTERN.search(str(interaction.get("resulted_in") or ""))
        if not match:
            continue
        page_key = str(interaction.get("page_id") or interaction.get("_page_url") or interaction.get("page_url") or "unknown")
        counts = {key: int(value) for key, value in match.groupdict().items()}
        existing = pages.get(page_key)
        if not existing or sum(counts.values()) > sum(existing.values()):
            pages[page_key] = counts
    return pages


def _objective_assurance(journey: dict, interactions: list[dict]) -> dict:
    hints = journey.get("test_hints") or {}
    objective = str(hints.get("journey_objective") or hints.get("objective") or "")
    targets = [str(item) for item in (hints.get("objective_targets") or []) if str(item).strip()]
    searchable = [_normalise(" ".join(str(item.get(key) or "") for key in ("element_label", "selector", "page_url", "_page_url", "destination_url", "resulted_in"))) for item in interactions]
    matched, missing = [], []
    for target in targets:
        target_text = _normalise(target)
        words = target_text.split()
        found = bool(target_text) and any(target_text in item or (words and all(word in item.split() for word in words)) for item in searchable)
        (matched if found else missing).append(target)
    return {
        "objective": objective, "targets": targets, "matched_targets": matched, "missing_targets": missing,
        "completion_percentage": _percentage(len(matched), len(targets)),
        "is_exhaustive_objective": any(word in objective.lower() for word in EXHAUSTIVE_WORDS),
    }


def _risk_profile(journey: dict, interactions: list[dict]) -> dict:
    objective = str((journey.get("test_hints") or {}).get("journey_objective") or "")
    labels = " ".join(str(item.get("element_label") or "") for item in interactions)
    corpus = _normalise(f"{objective} {labels}")
    high = ("purchase", "payment", "checkout", "delete", "submit", "account", "personal", "claim")
    medium = ("login", "sign in", "configuration", "preference", "report", "upload", "download", "admin")
    if any(word in corpus for word in high):
        return {"level": "high", "basis": "inferred", "reason": "Potential financial, destructive, account, or personal-data capability."}
    if any(word in corpus for word in medium):
        return {"level": "medium", "basis": "inferred", "reason": "Authentication, configuration, reporting, or data-transfer capability."}
    return {"level": "low", "basis": "inferred", "reason": "Primarily navigational based on captured labels; owner confirmation is still required."}


def build_business_assurance(journey: dict, exploration_metadata: dict | None = None) -> dict:
    """Build an evidence-backed business coverage and assurance summary."""
    metadata = exploration_metadata or journey.get("exploration_metadata") or {}
    interactions = _flatten_interactions(journey)
    scans = _page_scan_inventory(interactions)
    unique_pages = {str(step.get("page_url") or "") for step in journey.get("steps") or [] if isinstance(step, dict) and step.get("page_url")}
    state_fingerprints = {fingerprint for item in interactions for fingerprint in (item.get("state_fingerprint_before"), item.get("state_fingerprint_after")) if fingerprint}
    actionable = [item for item in interactions if str(item.get("action") or "").lower() in CONTROL_ACTIONS]
    control_keys = {_control_key(item) for item in actionable if _control_key(item)}
    successful = [item for item in actionable if not any(word in str(item.get("resulted_in") or item.get("element_state_after") or "").lower() for word in FAILURE_WORDS)]
    failed = [item for item in actionable if item not in successful]
    successful_keys = {_control_key(item) for item in successful if _control_key(item)}
    key_counts = Counter(_control_key(item) for item in actionable if _control_key(item))
    duplicate_attempts = sum(count - 1 for count in key_counts.values() if count > 1)

    discovered_buttons = sum(item.get("buttons", 0) for item in scans.values())
    discovered_links = sum(item.get("links", 0) for item in scans.values())
    discovered_inputs = sum(item.get("inputs", 0) for item in scans.values())
    estimated_controls = discovered_buttons + discovered_links + discovered_inputs or len(control_keys)
    explored_links = {_control_key(item) for item in actionable if str(item.get("element_type") or "").lower() in {"a", "link"} and _control_key(item)}
    coverage_percentage = _percentage(len(successful_keys), estimated_controls)
    link_coverage_percentage = _percentage(len(explored_links), discovered_links)
    attempted_controls = len(control_keys)
    succeeded_controls = len(successful_keys)
    failed_controls = len(failed)
    unexplored_controls = max(0, estimated_controls - succeeded_controls)
    explored_link_count = len(explored_links)
    skipped_controls: int | None = None
    external_links: int | None = None
    denominator_quality = "estimated_from_page_scan" if scans else "derived_from_captured_interactions"

    hints = journey.get("test_hints") or {}
    candidate_ledger = [item for item in (hints.get("candidate_ledger") or []) if isinstance(item, dict)]
    if candidate_ledger:
        in_scope = [item for item in candidate_ledger if str(item.get("status") or "") != "external"]
        succeeded_candidates = [item for item in in_scope if str(item.get("status") or "") == "succeeded"]
        attempted_candidates = [item for item in in_scope if str(item.get("status") or "") in {"attempted", "succeeded", "failed"}]
        failed_candidates = [item for item in in_scope if str(item.get("status") or "") == "failed"]
        skipped_candidates = [item for item in in_scope if str(item.get("status") or "").startswith("skipped")]
        unexplored_candidates = [item for item in in_scope if str(item.get("status") or "") == "discovered"]
        link_candidates = [item for item in in_scope if str(item.get("tag") or "").lower() == "a" or bool(item.get("href"))]
        explored_link_candidates = [item for item in link_candidates if str(item.get("status") or "") == "succeeded"]
        estimated_controls = len(in_scope)
        attempted_controls = len(attempted_candidates)
        succeeded_controls = len(succeeded_candidates)
        failed_controls = len(failed_candidates)
        skipped_controls = len(skipped_candidates)
        external_links = sum(str(item.get("status") or "") == "external" for item in candidate_ledger)
        unexplored_controls = len(unexplored_candidates)
        discovered_links = len(link_candidates)
        explored_link_count = len(explored_link_candidates)
        coverage_percentage = _percentage(succeeded_controls, estimated_controls)
        link_coverage_percentage = _percentage(explored_link_count, discovered_links)
        denominator_quality = "captured_candidate_ledger"

    objective = _objective_assurance(journey, interactions)
    outcome_text = _normalise(f"{journey.get('outcome')} {journey.get('outcome_detail')}")
    capture_blocked = any(word in outcome_text for word in ("blocked", "failed", "fallback"))
    if capture_blocked:
        completion_status = "blocked"
    elif objective["completion_percentage"] == 100 and not failed:
        completion_status = "verified"
    elif objective["completion_percentage"] not in (None, 0) or successful:
        completion_status = "partial"
    else:
        completion_status = "unverified"

    screenshots = sum(bool(item.get("screenshot_before") or item.get("screenshot_after")) for item in interactions)
    dom_snapshots = sum(bool(item.get("dom_snapshot_before") or item.get("dom_snapshot_after")) for item in interactions)
    timestamps = sum(bool(item.get("event_timestamp")) for item in interactions)
    event_ids = sum(bool(item.get("event_id")) for item in interactions)
    network_events = [event for item in interactions for event in (item.get("network_events") or []) if isinstance(event, dict)]
    roles = sum(bool(item.get("role")) for item in interactions)
    validation_messages = sum(bool(item.get("validation_message")) for item in interactions)
    input_values = sum(bool(item.get("value")) for item in interactions if str(item.get("action") or "").lower() in {"fill", "type", "input", "select"})
    browser, viewport = str(metadata.get("browser") or "unknown"), metadata.get("viewport") or {}
    domains = [
        {"name": "Evidence traceability", "status": "covered" if event_ids and (screenshots or dom_snapshots) else "partial", "detail": f"{event_ids} event IDs, {screenshots} screenshot-backed events, and {dom_snapshots} DOM-backed events."},
        {"name": "Role and permission coverage", "status": "not_assessed", "detail": "One browser session was captured; a persona and permission matrix was not executed."},
        {"name": "Privacy and data handling", "status": "review_required" if dom_snapshots or input_values else "not_assessed", "detail": "Raw DOM/screenshots may contain user-visible data; automated redaction and retention policy are not proven."},
        {"name": "Accessibility", "status": "partial" if roles else "not_assessed", "detail": f"{roles} semantic role references captured; automated WCAG checks were not executed."},
        {"name": "Performance", "status": "partial" if network_events else "not_assessed", "detail": f"{len(network_events)} network observations captured; timings and Core Web Vitals were not measured."},
        {"name": "Browser and viewport compatibility", "status": "single_environment", "detail": f"Captured in {browser} at {viewport.get('width', '?')} x {viewport.get('height', '?')}; no compatibility matrix was run."},
        {"name": "Negative and validation coverage", "status": "partial" if validation_messages or failed else "not_assessed", "detail": f"{validation_messages} validation messages and {len(failed)} failed or blocked actions observed."},
    ]
    recommendations = []
    if objective["missing_targets"]:
        recommendations.append(f"Explore missing objective targets: {', '.join(objective['missing_targets'])}.")
    if objective["is_exhaustive_objective"] and link_coverage_percentage != 100:
        recommendations.append("Continue until every discovered in-scope link is visited, skipped with reason, or blocked.")
    if failed:
        recommendations.append("Review failed or blocked controls and record an owner-approved disposition.")
    recommendations.extend([
        "Execute the journey for each applicable business role and permission level.",
        "Run accessibility, performance, and browser/viewport checks as separate assurance passes.",
        "Apply an approved evidence-retention and sensitive-data redaction policy before audit use.",
    ])
    evidence_score = 20 if event_ids and (screenshots or dom_snapshots) else 10 if interactions else 0
    objective_score = round((objective["completion_percentage"] or 0) * 0.35)
    action_score = round((succeeded_controls / attempted_controls * 15) if attempted_controls else 0)
    scope_measure = link_coverage_percentage if objective["is_exhaustive_objective"] else coverage_percentage
    scope_score = round((scope_measure or 0) * 0.20)
    readiness_score = min(90, evidence_score + objective_score + action_score + scope_score)
    readiness = "ready" if readiness_score >= 80 else "conditional" if readiness_score >= 60 else "needs_review"
    return {
        "version": "1.0", "readiness": readiness, "readiness_score": readiness_score,
        "completion_status": completion_status, "risk": _risk_profile(journey, interactions), "objective": objective,
        "coverage": {
            "pages_visited": len(unique_pages), "states_observed": len(state_fingerprints),
            "estimated_controls_discovered": estimated_controls, "controls_attempted": attempted_controls,
            "controls_succeeded": succeeded_controls, "controls_failed_or_blocked": failed_controls,
            "duplicate_attempts": duplicate_attempts, "estimated_unexplored_controls": unexplored_controls,
            "interaction_coverage_percentage": coverage_percentage, "links_discovered": discovered_links,
            "links_explored": explored_link_count, "link_coverage_percentage": link_coverage_percentage,
            "skipped_controls": skipped_controls, "external_links": external_links,
            "denominator_quality": denominator_quality,
        },
        "evidence": {"events": len(interactions), "event_ids": event_ids, "timestamps": timestamps, "screenshot_backed_events": screenshots, "dom_backed_events": dom_snapshots, "network_observations": len(network_events)},
        "domains": domains, "recommendations": list(dict.fromkeys(recommendations)),
        "limitations": ([
            "Skipped and external candidate totals are unknown for historical journeys because live planning events were not persisted.",
            "Coverage is estimated from captured page scans and requires business-owner review before certification.",
        ] if not candidate_ledger else [
            "Candidate coverage reflects controls visible during this run; controls hidden by role, data, viewport, or timing may not be represented.",
        ]) + [
            "Business criticality is inferred from labels and must be confirmed by the process owner.",
        ],
    }