from __future__ import annotations

import base64
import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from schemas.configuration_schema import JiraConfiguration
from services.artifact_file_service import write_json_file
from services.jira_client_service import JiraClientError, create_issue

logger = logging.getLogger('step5_reporting_module')

STATUS_FAILED = 'failed'
STATUS_PASSED = 'passed'
STATUS_SKIPPED = 'skipped'

PRIORITY_CRITICAL = 'Critical'
PRIORITY_HIGH = 'High'
PRIORITY_MEDIUM = 'Medium'


def _parse_component_from_uri(uri: str) -> str:
    try:
        parts = Path(uri.replace('\\', '/')).parts
        if 'features' in parts:
            idx = parts.index('features')
            if idx + 1 < len(parts):
                return parts[idx + 1]
    except Exception:
        pass
    return 'unknown-component'


def _parse_tags(tags: list) -> list[str]:
    return [str(tag.get('name', '')).lstrip('@') for tag in tags if tag.get('name')]


def _ns_to_seconds(duration_ns: int) -> float:
    return round(duration_ns / 1_000_000_000, 3) if duration_ns else 0.0


def _process_steps(steps: list) -> dict[str, Any]:
    all_steps: list[dict[str, Any]] = []
    failed_step = None
    for step in steps:
        result = step.get('result', {})
        keyword = step.get('keyword', '').strip()
        name = step.get('name', '')
        status = result.get('status', STATUS_SKIPPED)
        duration_s = _ns_to_seconds(result.get('duration', 0))
        if keyword in ('Before', 'After') and not name:
            continue
        all_steps.append({
            'keyword': keyword,
            'name': name,
            'status': status,
            'duration_s': duration_s,
        })
        if status == STATUS_FAILED and not failed_step:
            failed_step = {
                'keyword': keyword,
                'name': name,
                'duration_s': duration_s,
                'error_message': result.get('error_message', ''),
                'status': STATUS_FAILED,
            }
    return {'all_steps': all_steps, 'failed_step': failed_step}


def _parse_source_from_error(error_message: str) -> dict[str, str]:
    source = {'file': 'unknown', 'line': 'unknown', 'package': 'local'}
    if not error_message:
        return source
    match = re.search(r'at\s+.*?\((.*?):(\d+:\d+)\)', error_message)
    if match:
        full_path = match.group(1).replace('\\', '/')
        source['file'] = full_path.split('/')[-1]
        source['line'] = match.group(2)
        if 'node_modules' in full_path:
            pkg_parts = full_path.split('node_modules/')[-1].split('/')
            source['package'] = f"{pkg_parts[0]}/{pkg_parts[1]}" if pkg_parts and pkg_parts[0].startswith('@') and len(pkg_parts) > 1 else pkg_parts[0]
    return source


def _determine_priority(failed_step: dict | None, total_steps: int) -> str:
    if not failed_step:
        return PRIORITY_MEDIUM
    step_name = str(failed_step.get('name', '')).lower()
    if any(kw in step_name for kw in ['sign in', 'login', 'authenticate', 'launch']):
        return PRIORITY_CRITICAL
    if total_steps > 0 and ((total_steps - 1) / total_steps) > 0.5:
        return PRIORITY_CRITICAL
    return PRIORITY_HIGH


def read_cucumber_json(file_path: str) -> list[dict[str, Any]]:
    incidents: list[dict[str, Any]] = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            report_data = json.load(f)
    except Exception as exc:
        logger.error('Failed reading Cucumber file at %s: %s', file_path, exc)
        return incidents

    for feature in report_data:
        feature_name = feature.get('name', '')
        feature_uri = feature.get('uri', '')
        feature_tags = _parse_tags(feature.get('tags', []))
        component = _parse_component_from_uri(feature_uri)

        for scenario in feature.get('elements', []):
            step_metrics = _process_steps(scenario.get('steps', []))
            failed_step = step_metrics['failed_step']
            if not failed_step:
                continue

            all_steps = step_metrics['all_steps']
            total_steps = len(all_steps)
            error_msg = failed_step.get('error_message', '')
            incident = {
                'feature_name': feature_name,
                'scenario_name': scenario.get('name', ''),
                'scenario_id': scenario.get('id', ''),
                'component': component,
                'feature_file': Path(feature_uri).name,
                'tags': list(set(feature_tags + _parse_tags(scenario.get('tags', [])))),
                'failed_step': failed_step,
                'all_steps': all_steps,
                'error_message': error_msg,
                'error_type': error_msg.split(':')[0] if ':' in error_msg else 'UnknownError',
                'source': _parse_source_from_error(error_msg),
                'priority': _determine_priority(failed_step, total_steps),
                'total_steps': total_steps,
                'steps_passed': sum(1 for s in all_steps if s['status'] == STATUS_PASSED),
                'suite_duration_s': sum(s['duration_s'] for s in all_steps),
            }
            incidents.append(build_jira_payload(incident))

    logger.info('Parsed %s failures from %s', len(incidents), file_path)
    return incidents


def build_jira_payload(incident: dict[str, Any]) -> dict[str, Any]:
    failed_step = incident.get('failed_step', {})
    source = incident.get('source', {})
    tags = incident.get('tags', [])
    scenario_clean = re.sub(r'[^A-Za-z\s]', ' ', incident.get('scenario_name', ''))
    icon_map = {STATUS_PASSED: '✅', STATUS_FAILED: '❗', STATUS_SKIPPED: '⚠️'}
    step_lines = [
        f"{icon_map.get(s.get('status', STATUS_SKIPPED))} {s.get('keyword', '')} {s.get('name', '')}{'  ← FAILED HERE' if s.get('status') == STATUS_FAILED else ''}".strip()
        for s in incident.get('all_steps', [])
    ]
    description = f"""
## Incident Summary
Feature      : {incident.get('feature_name', '')}
Scenario ID  : {incident.get('scenario_id', 'N/A')}
Feature File : {incident.get('feature_file', '')}

## Environment & Tags
Application  : {next((t.upper() for t in tags if t in ['wdw','dlr']), 'WDW')}
Auth State   : {'Authenticated' if 'auth' in tags else 'Guest'}
Run DateTime : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Tags         : {', '.join(tags)}

## Failure Details
Failed Step    : {failed_step.get('keyword', '')} {failed_step.get('name', '')}
Step Number    : {incident.get('steps_passed', 0) + 1} of {incident.get('total_steps', 0)}
Error Type     : {incident.get('error_type', '')}
Error Message  : {incident.get('error_message', '')}
Source File    : {source.get('file', 'N/A')}:{source.get('line', 'N/A')}
Package        : {source.get('package', 'local')}

## Full Step Execution Log
{chr(10).join(step_lines)}
""".strip()
    return {
        'summary': f'{scenario_clean}',
        'description': description,
        'issue_type': 'Bug',
        'priority': incident.get('priority', PRIORITY_HIGH),
        'labels': list(set(tags + ['automated', 'qa-regression'])),
        'component': incident.get('component', ''),
        'dedup_key': f"{incident.get('feature_file', '')}|{scenario_clean}|{incident.get('error_type', '')}".lower(),
    }


def process_reports(json_path: str) -> list[dict[str, Any]]:
    all_payloads: list[dict[str, Any]] = []
    path_obj = Path(json_path)
    if not path_obj.exists():
        logger.warning('Provided path does not exist: %s', json_path)
        return all_payloads
    if path_obj.is_dir():
        for j_file in path_obj.rglob('*.json'):
            all_payloads.extend(read_cucumber_json(str(j_file)))
    elif path_obj.is_file() and path_obj.suffix == '.json':
        all_payloads.extend(read_cucumber_json(str(path_obj)))
    logger.info('Pipeline processed %s total JIRA issue payloads.', len(all_payloads))
    return all_payloads


def save_payloads_to_disk(payloads: list[dict[str, Any]], output_dir: str) -> str | None:
    if not payloads:
        return None
    try:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        filename = f"jira_payloads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        full_path = Path(output_dir) / filename
        full_path.write_text(json.dumps(payloads, indent=4, ensure_ascii=False), encoding='utf-8')
        return str(full_path)
    except Exception as exc:
        logger.error('Failed writing payload array to disk: %s', exc)
        return None


def push_bugs_to_jira(payloads: list[dict[str, Any]], jira_config: JiraConfiguration) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for payload in payloads:
        try:
            result = create_issue(
                jira_config,
                summary=payload['summary'],
                description=payload['description'],
                labels=payload['labels'],
                issue_type=payload.get('issue_type', 'Bug'),
                acceptance_criteria=[],
            )
            results.append({**payload, **result, 'sync_status': 'synced'})
        except JiraClientError as exc:
            results.append({**payload, 'sync_status': 'failed', 'error': str(exc)})
    return results


async def run_reporting_pipeline(report_path: str, output_dir: str, jira_config: JiraConfiguration | None = None, push_to_jira: bool = False) -> dict[str, Any]:
    payloads = process_reports(report_path)
    saved_path = save_payloads_to_disk(payloads, output_dir)
    jira_results = []
    if push_to_jira and jira_config is not None:
        jira_results = push_bugs_to_jira(payloads, jira_config)
    return {
        'report_path': report_path,
        'payloads': payloads,
        'count': len(payloads),
        'saved_path': saved_path,
        'jira_results': jira_results,
    }
