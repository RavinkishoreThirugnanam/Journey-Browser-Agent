def journey_to_mermaid(journey: dict) -> str:
    lines = ["flowchart TD"]
    previous = "Start"
    lines.append('    Start["Start"]')
    steps = journey.get('steps', [])
    if steps and isinstance(steps[0], dict) and 'interactions' in steps[0]:
        node_index = 1
        for step in steps:
            step_label = f"{step.get('page_title', 'Step')}"
            node = f"N{node_index}"
            lines.append(f'    {node}["{step_label}"]')
            lines.append(f"    {previous} --> {node}")
            previous = node
            for interaction in step.get('interactions', [])[:3]:
                node_index += 1
                child = f"N{node_index}"
                label = f"{interaction.get('element_label', '')} {interaction.get('action', '')}".strip().replace('"', "'")
                lines.append(f'    {child}["{label}"]')
                lines.append(f"    {previous} --> {child}")
                previous = child
            node_index += 1
    else:
        for index, step in enumerate(steps, start=1):
            node = f"N{index}"
            label = step.get("page", "").replace('"', "'")
            lines.append(f'    {node}["{label}: {step.get("action", "")}"]')
            lines.append(f"    {previous} --> {node}")
            previous = node
    lines.append(f"    {previous} --> End[\"End\"]")
    return "\n".join(lines)
