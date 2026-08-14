import re
from html import unescape


def _snapshot_document_title(interactions: list[dict]) -> str:
    for interaction in interactions:
        for field in ('dom_snapshot_after', 'dom_snapshot_before'):
            snapshot = interaction.get(field)
            if not snapshot:
                continue
            match = re.search(r'<title\b[^>]*>(.*?)</title>', str(snapshot), re.IGNORECASE | re.DOTALL)
            if match:
                title = re.sub(r'<[^>]+>', ' ', match.group(1))
                title = re.sub(r'\s+', ' ', unescape(title)).strip()
                if title:
                    return title
    return ''


def _mermaid_payload(journey: dict) -> dict:
    """Exclude raw DOM and screenshots so navigation chrome cannot become diagram labels."""
    steps = []
    for step in journey.get('steps', []) or []:
        if not isinstance(step, dict):
            continue
        raw_interactions = [item for item in (step.get('interactions', []) or []) if isinstance(item, dict)]
        snapshot_title = _snapshot_document_title(raw_interactions)
        interactions = []
        for interaction in raw_interactions:
            interactions.append({
                'action': interaction.get('action'),
                'element_label': interaction.get('element_label'),
                'resulted_in': interaction.get('resulted_in'),
                'destination_url': interaction.get('destination_url'),
            })
        steps.append({
            'step_number': step.get('step_number'),
            'page_title': snapshot_title or step.get('page_title'),
            'page_url': step.get('page_url'),
            'interactions': interactions,
        })
    return {
        'journey_id': journey.get('journey_id'),
        'journey_title': journey.get('journey_title'),
        'objective': journey.get('objective') or (journey.get('test_hints') or {}).get('journey_objective'),
        'starting_url': journey.get('starting_url'),
        'outcome': journey.get('outcome'),
        'outcome_detail': journey.get('outcome_detail'),
        'steps': steps,
    }


def _normalise_mermaid(raw: str) -> str:
    """Keep only one Mermaid diagram and remove accidental LLM commentary."""
    text = str(raw or '').strip()
    match = re.search(r"```(?:mermaid)?\s*(flowchart\s+TD[\s\S]*?)```", text, re.IGNORECASE)
    if match:
        text = match.group(1).strip()
    else:
        start = re.search(r"flowchart\s+TD", text, re.IGNORECASE)
        if start:
            text = text[start.start():].strip()
    if not text.lower().startswith('flowchart td'):
        raise ValueError('LLM did not return a Mermaid flowchart TD diagram')
    return text


def journey_to_mermaid(journey: dict) -> str:
    """Build the same evidence-driven topology for every saved journey.

    Visualization used to be delegated to an LLM, so identical evidence could
    produce different levels of detail on separate requests. Keep the LLM for
    narrative generation elsewhere, but make journey maps reproducible and
    directly traceable to captured browser evidence.
    """
    return _journey_to_mermaid_fallback(journey)


def _semantic_label(value: object, fallback: str = 'Journey') -> str:
    label = unescape(str(value or '')).replace('&', ' and ')
    label = re.sub(r'(?i)\s*-?\s*press enter.*$', '', label)
    label = label.replace('"', '').replace("'", '')
    label = re.sub(r'[^A-Za-z0-9 +:.,()/-]+', ' ', label)
    label = re.sub(r'\s+', ' ', label).strip(' .-')
    return label[:120] or fallback


def _interaction_semantic_label(interaction: dict) -> str:
    action = str(interaction.get('action') or '').strip().lower()
    raw_label = _semantic_label(interaction.get('element_label'), action.title() or 'Action')
    value = _semantic_label(interaction.get('value'), '') if interaction.get('value') not in (None, '') else ''
    if action == 'fill':
        return f'Enter {raw_label}'
    if action == 'select':
        return f'Select {value or raw_label}'
    if action == 'validate':
        return f'Validate {raw_label}'
    if action == 'error':
        return f'Error: {raw_label}'
    return raw_label


def _semantic_path(journey: dict) -> list[str]:
    """Convert captured interactions to a concise business-readable branch."""
    supported_actions = {'open', 'hover', 'click', 'fill', 'select', 'navigate', 'validate', 'error'}
    noise = ('page scan', 'full page inventory', 'visible control', 'skip navigation', 'press enter to navigate')
    path = [_semantic_label(journey.get('journey_title') or journey.get('starting_point'), 'Journey')]
    seen: set[tuple[str, str, str]] = set()

    for step in journey.get('steps', []) or []:
        if not isinstance(step, dict):
            continue
        for interaction in step.get('interactions', []) or []:
            if not isinstance(interaction, dict):
                continue
            action = str(interaction.get('action') or '').strip().lower()
            raw = str(interaction.get('element_label') or '').strip()
            if action not in supported_actions or any(item in raw.lower() for item in noise):
                continue
            label = _interaction_semantic_label(interaction)
            destination = str(interaction.get('destination_url') or '').rstrip('/').lower()
            key = (action, label.lower(), destination)
            if key in seen or label.lower() == path[-1].lower():
                continue
            seen.add(key)
            path.append(label)

            result = str(interaction.get('resulted_in') or '').strip()
            normalized_result = result.lower().replace('_', ' ')
            if result and not any(term in normalized_result for term in (
                'page load', 'navigated', 'new page', 'menu revealed', 'no change', 'captured',
            )):
                result_label = _semantic_label(normalized_result.title(), '')
                if result_label and result_label.lower() != path[-1].lower():
                    path.append(result_label)
            api_trigger = str(interaction.get('api_call_triggered') or '').strip()
            if api_trigger:
                method = str(interaction.get('api_method') or '').strip().upper()
                status = str(interaction.get('api_response_status') or '').strip()
                trigger_label = _semantic_label(api_trigger.split('?', 1)[0], 'API call')
                api_label = f'API {method}: {trigger_label}' if method else f'API: {trigger_label}'
                if status:
                    api_label += f' ({status})'
                if api_label.lower() != path[-1].lower():
                    path.append(api_label)
        if len(path) >= 42:
            break
    return path[:42]


def _terminal_for_journey(journey: dict) -> tuple[str, str]:
    outcome = str(journey.get('outcome') or '').lower()
    detail = str(journey.get('outcome_detail') or '').lower()
    combined = f'{outcome} {detail}'
    if any(term in combined for term in ('human input', 'authentication', 'authorization', 'confirmation required', 'accept invite')):
        return 'HIR', 'Human Input Required'
    if 'blocked' in combined:
        return 'BLOCK', 'Exploration Blocked'
    if 'error' in combined or 'failed' in combined:
        return 'ERROR', 'Error'
    return 'COMP', 'Completed'


def journeys_to_mermaid(journeys: list[dict], root_feature: str) -> str:
    """Build one reproducible reference-style map from multiple saved journeys.

    A prefix tree merges shared scenario/action paths. Each captured journey
    retains its own outcome so incomplete exploration is never shown as complete.
    """
    root: dict = {'children': {}, 'terminals': []}
    for journey in journeys:
        cursor = root
        for label in _semantic_path(journey):
            cursor = cursor['children'].setdefault(label, {'children': {}, 'terminals': []})
        cursor['terminals'].append(_terminal_for_journey(journey))

    lines = [
        'flowchart TD',
        '    A["Start"]',
        f'    B["{_semantic_label(root_feature, "Consolidated Journey Map")}"]',
        '    A --> B',
    ]
    node_counter = 0
    terminal_counter = 0

    def emit(parent_id: str, node: dict) -> None:
        nonlocal node_counter, terminal_counter
        for label, child in node['children'].items():
            node_counter += 1
            child_id = f'N{node_counter}'
            lines.append(f'    {child_id}["{label}"]')
            lines.append(f'    {parent_id} --> {child_id}')
            emit(child_id, child)
        for prefix, label in node['terminals']:
            terminal_counter += 1
            terminal_id = f'{prefix}{terminal_counter}'
            lines.append(f'    {terminal_id}["{label}"]')
            lines.append(f'    {parent_id} --> {terminal_id}')

    emit('B', root)
    return '\n'.join(lines)


def _journey_to_mermaid_fallback(journey: dict) -> str:
    def clean_label(value: object, fallback: str = 'Journey') -> str:
        label = unescape(str(value or '')).replace('&', ' and ')
        label = re.sub(r'(?i)\s*-?\s*press enter.*$', '', label)
        label = label.replace("'", '')
        label = re.sub(r'[^A-Za-z0-9 +.-]+', ' ', label)
        label = re.sub(r'\s+', ' ', label).strip(' .-')
        return label[:100] or fallback

    def meaningful(interaction: dict) -> bool:
        action = str(interaction.get('action') or '').lower()
        label = str(interaction.get('element_label') or '').lower()
        if action not in {'hover', 'click', 'fill', 'select', 'navigate', 'validate', 'error'}:
            return False
        return not any(noise in label for noise in ('page scan', 'full page inventory', 'visible control'))

    def evidence_label(interaction: dict) -> str:
        """Return useful page evidence while excluding repeated navigation chrome."""
        if str(interaction.get('action') or '').lower() != 'inspect':
            return ''
        element_type = str(interaction.get('element_type') or '').lower()
        if element_type not in {'h1', 'h2', 'h3', 'heading', 'button', 'input', 'select', 'a', 'link'}:
            return ''
        raw_label = str(interaction.get('element_label') or '').strip()
        normalized = re.sub(r'\s+', ' ', raw_label).lower()
        if not normalized or any(noise in normalized for noise in (
            'press enter to navigate',
            'skip navigation',
            'log in or create account',
            'visit disney.com',
            'united states english',
            'page scan',
            'full page inventory',
        )):
            return ''
        prefix = 'Heading' if element_type in {'h1', 'h2', 'h3', 'heading'} else (
            'Input' if element_type in {'input', 'select'} else 'Control'
        )
        return f'{prefix}: {raw_label}'

    steps = [step for step in (journey.get('steps', []) or []) if isinstance(step, dict)]
    page_groups: dict[str, dict] = {}
    for step in steps:
        url = str(step.get('page_url') or '')
        group = page_groups.setdefault(url, {
            'title': step.get('page_title') or 'Captured Page',
            'actions': [],
            'evidence': [],
        })
        for interaction in (step.get('interactions', []) or []):
            if not isinstance(interaction, dict):
                continue
            if meaningful(interaction):
                group['actions'].append(interaction)
            observed = evidence_label(interaction)
            if observed:
                group['evidence'].append(observed)

    all_interactions = [interaction for group in page_groups.values() for interaction in group['actions']]
    first_hover = next((item for item in all_interactions if str(item.get('action')).lower() == 'hover'), None)
    root_label = clean_label(
        first_hover.get('element_label') if first_hover else journey.get('starting_point') or journey.get('journey_title'),
        'Journey',
    )
    outcome = str(journey.get('outcome') or '').lower()
    outcome_detail = str(journey.get('outcome_detail') or '').lower()
    if any(term in outcome_detail for term in ('authentication', 'authorization', 'human input', 'confirmation required', 'accept invite')):
        terminal_prefix, terminal_label = 'HIR', 'Human Input Required'
    elif 'blocked' in outcome:
        terminal_prefix, terminal_label = 'BLOCK', 'Exploration Blocked'
    else:
        terminal_prefix, terminal_label = 'COMP', 'Completed'

    objective = clean_label(
        (journey.get('test_hints') or {}).get('journey_objective') or journey.get('objective'),
        root_label,
    )
    lines = [
        'flowchart TD',
        '    START["Start"]',
        f'    OBJECTIVE["Objective: {objective}"]',
        '    START --> OBJECTIVE',
    ]
    node_index = 0
    terminal = f'{terminal_prefix}1'
    lines.append(f'    {terminal}["{terminal_label}"]')
    terminal_sources: list[str] = []
    total_evidence_count = 0

    for page_number, (url, group) in enumerate(page_groups.items(), start=1):
        page_node = f'PAGE{page_number}'
        page_title = clean_label(group.get('title'), f'Captured Page {page_number}')
        lines.append(f'    {page_node}["Page {page_number}: {page_title}"]')
        lines.append(f'    OBJECTIVE --> {page_node}')

        previous = page_node
        seen_actions: set[tuple[str, str, str]] = set()
        for interaction in group.get('actions', []):
            action = str(interaction.get('action') or 'action').strip().title()
            label = clean_label(interaction.get('element_label'), action)
            destination = str(interaction.get('destination_url') or '').rstrip('/').lower()
            key = (action.lower(), label.lower(), destination)
            if key in seen_actions:
                continue
            seen_actions.add(key)
            node_index += 1
            action_node = f'ACTION{node_index}'
            lines.append(f'    {action_node}["{action}: {label}"]')
            lines.append(f'    {previous} --> {action_node}')
            previous = action_node
        terminal_sources.append(previous)

        seen_evidence: set[str] = set()
        evidence_count = 0
        for label in group.get('evidence', []):
            if total_evidence_count >= 30:
                break
            cleaned = clean_label(label)
            key = cleaned.lower()
            if key in seen_evidence or cleaned.lower() == page_title.lower():
                continue
            seen_evidence.add(key)
            evidence_count += 1
            if evidence_count > 10:
                break
            total_evidence_count += 1
            evidence_node = f'EVIDENCE{page_number}_{evidence_count}'
            lines.append(f'    {evidence_node}["{cleaned}"]')
            lines.append(f'    {page_node} --> {evidence_node}')

    if not page_groups:
        lines.append('    OBJECTIVE --> NODATA["No browser page evidence captured"]')
        terminal_sources.append('NODATA')
    for source in dict.fromkeys(terminal_sources):
        lines.append(f'    {source} --> {terminal}')
    return '\n'.join(lines)
