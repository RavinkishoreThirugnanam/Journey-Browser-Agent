from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from core.config import BASE_DIR, STORAGE_DIR
from services.token_manager import TokenManager

logger = logging.getLogger('step6_summary')

SYSTEM_PROMPT = """You are a senior pipeline summary agent for enterprise test automation.

Your task is to read the outputs of the previous pipeline stages and write a concise but professional markdown summary.

Requirements:
- Preserve the meaning of the journey discovery, UI enrichment, user story, test case, test script, and reporting stages.
- Mention key counts, notable coverage areas, failures, and execution quality.
- Use the run metadata and token usage summaries when present.
- Highlight Jira sync or reporting outcomes when present.
- Produce a clean markdown report with sections and bullet points.
- Do not invent results that are not supported by the input.
- Write in a style suitable for engineering and QA leadership.
"""


def load_config() -> dict[str, Any]:
    config_path = BASE_DIR / 'config' / 'summary_config.json'
    try:
        return json.loads(config_path.read_text(encoding='utf-8'))
    except Exception as exc:
        logger.warning('Failed to load %s: %s', config_path, exc)
        return {
            'input_directory': str(STORAGE_DIR / 'generated_files'),
            'files': {},
            'openai_settings': {'model_name': 'gpt-4o-mini'},
            'output_file': 'summary.md',
        }


def read_file_content(directory: str, filename: str) -> str:
    if not filename:
        return '[WARNING: Filename missing in config]'

    filepath = Path(directory) / filename
    try:
        raw = filepath.read_text(encoding='utf-8')
    except FileNotFoundError:
        logger.warning("File '%s' not found in '%s'.", filename, directory)
        return f"[WARNING: File '{filename}' not found in '{directory}']"
    except Exception as exc:
        logger.error("Unexpected error reading '%s': %s", filename, exc)
        return f"[ERROR: Could not read '{filename}': {exc}]"

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw

    if isinstance(data, dict) and 'run_metadata' in data:
        return json.dumps(data['run_metadata'], indent=2, ensure_ascii=False)
    return raw


def build_summary_prompt(context: str) -> str:
    return f"{SYSTEM_PROMPT}\n\nHere are the input files mapped to their specific roles to analyse:\n\n{context}"


async def initialise_llm(openai_settings: dict[str, Any]) -> Any | None:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        logger.warning('langchain_openai is not installed; Step 6 will use a local markdown fallback.')
        return None

    model_name = (openai_settings.get('model_name', '') or 'gpt-4o-mini').strip()
    base_url = os.environ.get('OPENAI_BASE_URL') or os.environ.get('OPENAI_API_BASE') or ''

    token_manager = TokenManager()
    openai_api_key = token_manager.get_valid_token()
    if asyncio.iscoroutine(openai_api_key):
        openai_api_key = await openai_api_key

    if not openai_api_key:
        logger.warning('OpenAI API key could not be retrieved; Step 6 will use a local markdown fallback.')
        return None

    kwargs: dict[str, Any] = {
        'model': model_name,
        'api_key': openai_api_key,
    }
    if base_url:
        kwargs['base_url'] = base_url.rstrip('/')

    logger.info('Initialising OpenAI ChatOpenAI client -> %s', model_name)
    return ChatOpenAI(**kwargs)


def build_context(config: dict[str, Any], input_dir: str) -> str:
    files = config.get('files', {}) or {}
    sections = [
        ('1. BROWSER AGENT EXPLORATION DATA', files.get('browser_exploration')),
        ('2. BROWSER AGENT COST DATA (run_metadata)', files.get('browser_cost')),
        ('3. USER STORY EXPLORATION AND COST DATA (token_usage_summary)', files.get('user_story')),
        ('4. TEST CASE SUMMARY AND COST DATA', files.get('test_case')),
        ('5. TEST SCRIPT SUMMARY AND COST DATA', files.get('test_script')),
        ('6. REPORTING AND JIRA SUMMARY DATA', files.get('reporting')),
    ]

    context_parts: list[str] = []
    for title, filename in sections:
        context_parts.append(f'=== {title} ===')
        context_parts.append(read_file_content(input_dir, filename))
        context_parts.append('')
    return '\n'.join(context_parts).strip()


def build_local_summary(context: str) -> str:
    lower_context = context.lower()
    sections = {
        'browser': lower_context.count('browser agent'),
        'journey': lower_context.count('journey'),
        'story': lower_context.count('user story'),
        'test case': lower_context.count('test case'),
        'script': lower_context.count('test script'),
        'jira': lower_context.count('jira'),
    }

    return '\n'.join([
        '# Pipeline Summary',
        '',
        '## Overview',
        '- Step 6 generated a deterministic summary because the optional LLM client was unavailable.',
        '- The pipeline context was loaded successfully from prior step artifacts.',
        '',
        '## Detected Signals',
        *[f'- {name.title()}: {count}' for name, count in sections.items()],
        '',
        '## Notes',
        '- Verify OPENAI_API_KEY, optional OPENAI_BASE_URL, and langchain_openai installation if LLM-generated summaries are required.',
        '- This fallback keeps the application bootable and still produces a readable report artifact.',
    ])


async def render_summary(full_context: str, openai_settings: dict[str, Any]) -> str:
    llm = await initialise_llm(openai_settings)
    if llm is None:
        return build_local_summary(full_context)

    logger.info('Sending pipeline context to OpenAI summary model...')
    response = await llm.ainvoke(build_summary_prompt(full_context))
    return getattr(response, 'content', str(response))


async def generate_summary() -> dict[str, Any]:
    load_dotenv()
    config = load_config()
    input_dir = config.get('input_directory', str(STORAGE_DIR / 'generated_files'))
    openai_settings = config.get('openai_settings', {})
    output_file = config.get('output_file', 'summary.md')

    full_context = build_context(config, input_dir)
    report = await render_summary(full_context, openai_settings)
    output_path = Path(input_dir) / output_file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding='utf-8')

    logger.info('Report successfully generated and saved to -> %s', output_path)
    return {
        'output_file': str(output_path),
        'report': report,
    }


async def run_summary_pipeline(output_dir: str | None = None) -> dict[str, Any]:
    if output_dir:
        config = load_config()
        config['input_directory'] = output_dir
        config.setdefault('output_file', 'summary.md')
        config.setdefault('openai_settings', {'model_name': 'gpt-4o-mini'})
        full_context = build_context(config, output_dir)
        report = await render_summary(full_context, config.get('openai_settings', {}))
        output_path = Path(output_dir) / config.get('output_file', 'summary.md')
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding='utf-8')
        return {'output_file': str(output_path), 'report': report}

    return await generate_summary()


if __name__ == '__main__':
    asyncio.run(generate_summary())
