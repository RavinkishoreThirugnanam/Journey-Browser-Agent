from pathlib import Path
p = Path(r'backend/services/jira_client_service.py')
c = p.read_text()
old = """def create_story_issue(config: JiraConfiguration, *, summary: str, description: str, labels: list[str], acceptance_criteria: list[str]) -> dict[str, str]:
    formatted_acceptance = '\n'.join(f'- {line}' for line in acceptance_criteria if line)
    fields = {
        'project': {'key': config.project_key},
        'summary': summary,
        'description': f"{description}\n\nAcceptance Criteria:\n{formatted_acceptance}",
        'issuetype': {'name': config.issue_type or 'Story'},
        'labels': labels,
    }
    response = _request(config, 'POST', '/rest/api/3/issue', json={'fields': fields})
"""
new = """def _text_node(text: str) -> dict[str, object]:
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
        content.append({
            'type': 'bulletList',
            'content': [_bullet_list_item(line) for line in acceptance_criteria if line],
        })
    if not content:
        content = [_paragraph('')]
    return {
        'type': 'doc',
        'version': 1,
        'content': content,
    }


def create_story_issue(config: JiraConfiguration, *, summary: str, description: str, labels: list[str], acceptance_criteria: list[str]) -> dict[str, str]:
    fields = {
        'project': {'key': config.project_key},
        'summary': summary,
        'description': _build_adf(description, acceptance_criteria),
        'issuetype': {'name': config.issue_type or 'Story'},
        'labels': labels,
    }
    response = _request(config, 'POST', '/rest/api/3/issue', json={'fields': fields})
"""
if old not in c:
    raise SystemExit('target block not found')
p.write_text(c.replace(old, new))
