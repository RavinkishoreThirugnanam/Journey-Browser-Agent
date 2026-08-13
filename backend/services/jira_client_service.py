from __future__ import annotations

import base64
from typing import Any
from urllib.parse import quote

import requests

from schemas.configuration_schema import JiraConfiguration


class JiraClientError(RuntimeError):
    pass


def _auth_headers(config: JiraConfiguration) -> dict[str, str]:
    if config.auth_type.lower() == 'basic':
        token = base64.b64encode(f'{config.username}:{config.api_token}'.encode('utf-8')).decode('utf-8')
        return {'Authorization': f'Basic {token}'}
    if config.auth_type.lower() == 'bearer':
        return {'Authorization': f'Bearer {config.api_token}'}
    raise JiraClientError(f'Unsupported Jira auth_type: {config.auth_type}')


def _request(config: JiraConfiguration, method: str, path: str, *, json: dict[str, Any] | None = None) -> requests.Response:
    if not config.base_url or not config.project_key:
        raise JiraClientError('Jira base_url and project_key are required')
    url = f"{config.base_url.rstrip('/')}{path}"
    try:
        return requests.request(
            method=method,
            url=url,
            headers={**_auth_headers(config), 'Accept': 'application/json', 'Content-Type': 'application/json'},
            json=json,
            timeout=20,
        )
    except requests.RequestException as exc:
        raise JiraClientError(f'Jira request failed for {config.base_url}: {exc}') from exc

def test_connection(config: JiraConfiguration) -> dict[str, str]:
    response = _request(config, 'GET', '/rest/api/3/myself')
    if response.status_code >= 400:
        raise JiraClientError(f'Jira connection failed: {response.status_code} {response.text[:200]}')
    payload = response.json()
    return {
        'account_id': str(payload.get('accountId') or payload.get('name') or ''),
        'display_name': str(payload.get('displayName') or ''),
        'email': str(payload.get('emailAddress') or ''),
    }


def _text_node(text: str) -> dict[str, object]:
    return {'type': 'text', 'text': text}


def _paragraph(text: str) -> dict[str, object]:
    return {'type': 'paragraph', 'content': [_text_node(text)]}


def _bullet_list_item(text: str) -> dict[str, object]:
    return {
        'type': 'listItem',
        'content': [
            {
                'type': 'paragraph',
                'content': [_text_node(text)],
            }
        ],
    }


def _build_adf(description: str, acceptance_criteria: list[str]) -> dict[str, object]:
    content: list[dict[str, object]] = []
    if description:
        content.append(_paragraph(description))
    if acceptance_criteria:
        content.append(_paragraph('Acceptance Criteria'))
        content.append({'type': 'bulletList', 'content': [_bullet_list_item(line) for line in acceptance_criteria if line]})
    if not content:
        content = [_paragraph('')]
    return {'type': 'doc', 'version': 1, 'content': content}


def create_issue(config: JiraConfiguration, *, summary: str, description: str, labels: list[str], issue_type: str, acceptance_criteria: list[str]) -> dict[str, str]:
    fields = {
        'project': {'key': config.project_key},
        'summary': summary,
        'description': _build_adf(description, acceptance_criteria),
        'issuetype': {'name': issue_type},
        'labels': labels,
    }
    response = _request(config, 'POST', '/rest/api/3/issue', json={'fields': fields})
    if response.status_code >= 400:
        raise JiraClientError(f'Jira issue creation failed: {response.status_code} {response.text[:300]}')
    payload = response.json()
    issue_key = str(payload.get('key') or '')
    browse_url = f"{config.base_url.rstrip('/')}/browse/{issue_key}" if issue_key else None
    return {'jira_key': issue_key, 'jira_url': browse_url or '', 'jira_issue_type': issue_type}


def create_story_issue(config: JiraConfiguration, *, summary: str, description: str, labels: list[str], acceptance_criteria: list[str]) -> dict[str, str]:
    return create_issue(config, summary=summary, description=description, labels=labels, issue_type=config.issue_type or 'Story', acceptance_criteria=acceptance_criteria)


def create_test_case_issue(config: JiraConfiguration, *, summary: str, description: str, labels: list[str], acceptance_criteria: list[str]) -> dict[str, str]:
    configured_type = (getattr(config, 'test_case_issue_type', '') or '').strip()
    # Test cases must not silently become Jira Stories. If a project lacks the
    # preferred test issue type, fall back to Task/Bug but never Story.
    if configured_type.lower() == 'story':
        configured_type = ''
    candidates = [
        configured_type,
        'Test',
        'Task',
        'Bug',
    ]
    seen: set[str] = set()
    last_error: JiraClientError | None = None
    for issue_type in candidates:
        issue_type = issue_type.strip()
        if not issue_type or issue_type in seen:
            continue
        seen.add(issue_type)
        try:
            return create_issue(config, summary=summary, description=description, labels=labels, issue_type=issue_type, acceptance_criteria=acceptance_criteria)
        except JiraClientError as exc:
            last_error = exc
            message = str(exc).lower()
            if 'issuetype' in message or 'issue type' in message or 'field' in message:
                continue
            raise
    if last_error:
        raise last_error
    raise JiraClientError('Unable to create Jira test case issue')


def _adf_node_text(node: Any) -> str:
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ''
    if node.get('type') == 'text':
        return str(node.get('text') or '')
    if node.get('type') == 'hardBreak':
        return '\n'
    return ''.join(_adf_node_text(child) for child in node.get('content') or [])


def _adf_blocks(document: Any) -> list[tuple[str, str]]:
    if isinstance(document, str):
        return [('paragraph', line.strip()) for line in document.splitlines() if line.strip()]
    if not isinstance(document, dict):
        return []

    blocks: list[tuple[str, str]] = []
    for node in document.get('content') or []:
        if not isinstance(node, dict):
            continue
        node_type = str(node.get('type') or '')
        if node_type in {'paragraph', 'heading'}:
            text = _adf_node_text(node).strip()
            if text:
                blocks.append((node_type, text))
        elif node_type in {'bulletList', 'orderedList'}:
            for list_item in node.get('content') or []:
                text = _adf_node_text(list_item).strip()
                if text:
                    blocks.append(('listItem', text))
        else:
            blocks.extend(_adf_blocks(node))
    return blocks


def _extract_description_and_acceptance(document: Any) -> tuple[str, list[str], bool]:
    blocks = _adf_blocks(document)
    marker_index = next((
        index for index, (_, text) in enumerate(blocks)
        if text.strip().rstrip(':').casefold() in {'acceptance criteria', 'acceptance criterion'}
    ), None)
    if marker_index is None:
        return '\n\n'.join(text for _, text in blocks).strip(), [], False

    description = '\n\n'.join(text for _, text in blocks[:marker_index]).strip()
    criteria = []
    for _, text in blocks[marker_index + 1:]:
        cleaned = text.strip().lstrip('-*• ').strip()
        if cleaned:
            criteria.append(cleaned)
    return description, criteria, True


def get_issue(config: JiraConfiguration, issue_key: str) -> dict[str, Any]:
    key = str(issue_key or '').strip()
    if not key:
        raise JiraClientError('Jira issue key is required')
    fields = 'summary,description,labels,updated'
    response = _request(config, 'GET', f'/rest/api/3/issue/{quote(key, safe="")}?fields={fields}')
    if response.status_code >= 400:
        raise JiraClientError(f'Jira issue retrieval failed for {key}: {response.status_code} {response.text[:300]}')
    payload = response.json()
    issue_fields = payload.get('fields') or {}
    description, acceptance_criteria, criteria_found = _extract_description_and_acceptance(issue_fields.get('description'))
    resolved_key = str(payload.get('key') or key)
    return {
        'jira_key': resolved_key,
        'jira_url': f"{config.base_url.rstrip('/')}/browse/{resolved_key}",
        'summary': str(issue_fields.get('summary') or ''),
        'description': description,
        'acceptance_criteria': acceptance_criteria,
        'acceptance_criteria_found': criteria_found,
        'labels': [str(label) for label in issue_fields.get('labels') or []],
        'updated': str(issue_fields.get('updated') or ''),
    }