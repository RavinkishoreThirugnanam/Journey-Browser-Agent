import re
from html import unescape

from services.agent_prompts import MERMAID_AGENT_PROMPT
from services.llm_generation_service import LLMGenerationError, generate_text_with_llm


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
    try:
        generated = generate_text_with_llm(
            MERMAID_AGENT_PROMPT,
            {'journey': _mermaid_payload(journey)},
        )
        return _normalise_mermaid(generated)
    except (LLMGenerationError, ValueError, KeyError, IndexError, TypeError):
        # Mermaid visualization must remain available when no LLM is configured.
        return _journey_to_mermaid_fallback(journey)


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
        if action not in {'hover', 'click', 'fill', 'select', 'scroll', 'navigate', 'validate', 'error'}:
            return False
        return not any(noise in label for noise in ('page scan', 'full page inventory', 'visible control'))

    steps = [step for step in (journey.get('steps', []) or []) if isinstance(step, dict)]
    starting_url = str(journey.get('starting_url') or '')
    page_groups: dict[str, dict] = {}
    for step in steps:
        url = str(step.get('page_url') or '')
        group = page_groups.setdefault(url, {'title': step.get('page_title') or 'Captured Page', 'interactions': []})
        group['interactions'].extend(
            interaction for interaction in (step.get('interactions', []) or [])
            if isinstance(interaction, dict) and meaningful(interaction)
        )

    all_interactions = [interaction for group in page_groups.values() for interaction in group['interactions']]
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

    lines = ['flowchart TD', '    A["Start"]', f'    A --> B["{root_label}"]']
    node_index = 0
    branch_index = 0
    attached_urls: set[str] = set()

    def append_branch(parent: str, labels: list[str]) -> None:
        nonlocal node_index, branch_index
        previous = parent
        for label in labels:
            node_index += 1
            node = f'N{node_index}'
            lines.append(f'    {node}["{clean_label(label)}"]')
            lines.append(f'    {previous} --> {node}')
            previous = node
        branch_index += 1
        terminal = f'{terminal_prefix}{branch_index}'
        lines.append(f'    {terminal}["{terminal_label}"]')
        lines.append(f'    {previous} --> {terminal}')

    start_group = page_groups.get(starting_url) or next(iter(page_groups.values()), {'interactions': []})
    start_clicks = [item for item in start_group['interactions'] if str(item.get('action')).lower() == 'click']
    seen_branches: set[tuple[str, str]] = set()
    for click in start_clicks:
        labels = [click.get('element_label') or 'Open Feature']
        destination = str(click.get('destination_url') or '')
        branch_key = (clean_label(labels[0]).lower(), destination.rstrip('/').lower())
        if branch_key in seen_branches:
            continue
        seen_branches.add(branch_key)
        destination_group = page_groups.get(destination)
        if destination_group:
            attached_urls.add(destination)
            destination_title = clean_label(destination_group['title'])
            if destination_title != clean_label(labels[0]):
                labels.append(destination_group['title'])
            labels.extend(
                item.get('element_label') or item.get('action')
                for item in destination_group['interactions']
                if str(item.get('action')).lower() != 'hover'
            )
        append_branch('B', [str(label) for label in labels if label])

    for url, group in page_groups.items():
        if url == starting_url or url in attached_urls:
            continue
        labels = [group['title']]
        labels.extend(item.get('element_label') or item.get('action') for item in group['interactions'])
        append_branch('B', [str(label) for label in labels if label])

    if not start_clicks and not branch_index:
        labels = [
            item.get('element_label') or item.get('action')
            for item in start_group.get('interactions', [])
            if str(item.get('action')).lower() != 'hover'
        ]
        append_branch('B', [str(label) for label in labels if label])
    return '\n'.join(lines)
