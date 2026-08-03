from __future__ import annotations

import re
import os
import asyncio
import inspect
import hashlib
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from routers.configuration_router import _read as read_configuration
from services.artifact_file_service import write_json_file, write_markdown_file, unique_filename, GENERATED_DIR
from services.business_assurance_service import build_business_assurance
from services.token_manager import TokenManager
from services.live_event_service import clear_events, publish_event
from services.live_browser_service import connect_live_browser, prepare_live_page, scroll_live_page, show_live_pointer
from services.agent_prompts import get_browser_agent_profile
from schemas.journey_schema import ExplorationMetadata, ExplorationResult, Interaction, JourneyRecord, JourneyStep
try:
    from services.playwright_mcp_service import explore_with_mcp
except Exception:
    explore_with_mcp = None

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover - optional dependency
    sync_playwright = None

try:  # pragma: no cover - optional dependency
    from browser_use import Agent, Browser, BrowserSession
    from browser_use.llm.openai.chat import ChatOpenAI as BrowserUseChatOpenAI
except Exception:  # pragma: no cover - optional dependency
    Agent = Browser = BrowserSession = BrowserUseChatOpenAI = None

try:  # pragma: no cover - optional dependency
    from langchain_openai import ChatOpenAI as LangChainChatOpenAI
except Exception:  # pragma: no cover - optional dependency
    LangChainChatOpenAI = None

try:  # pragma: no cover - optional dependency
    from langchain_core.messages import HumanMessage, SystemMessage
except Exception:  # pragma: no cover - optional dependency
    HumanMessage = SystemMessage = None


@dataclass
class ClickCandidate:
    index: int
    text: str = ''
    href: str = ''
    tag: str = ''
    role: str = ''
    element_id: str = ''
    selector: str = ''
    value: str = ''
    input_type: str = ''


def _effective_cdp_url(configured_url: object = '') -> str:
    """Prefer the Docker/runtime CDP endpoint over persisted UI defaults."""
    env_url = os.environ.get('BROWSER_CDP_URL', '').strip()
    configured = str(configured_url or '').strip()
    if env_url:
        return env_url
    if configured in {'', 'http://localhost:9222', 'http://127.0.0.1:9222'}:
        return 'http://browser-stream:9222'
    return configured


def _runtime_browser_config() -> dict[str, object]:
    config = read_configuration()
    llm = config.get('llm', {}) if isinstance(config, dict) else {}
    application = config.get('application', {}) if isinstance(config, dict) else {}
    token_manager = TokenManager()
    auth_token = str(llm.get('auth_token', '') or '').strip()
    if not auth_token:
        try:
            auth_token = token_manager.get_valid_token()
        except Exception:
            auth_token = ''
    return {
        'browser_use_enabled': bool(llm.get('browser_use_enabled', True)),
        'browser_model': llm.get('model', 'gpt-4o-mini'),
        'supervisor_model': llm.get('supervisor_model') or llm.get('model', 'gpt-4o-mini'),
        'api_endpoint': llm.get('api_endpoint', '') or config.get('llm_api_endpoint', ''),
        'auth_token': auth_token,
        'temperature': llm.get('temperature', 0.2),
        'browser_timeout_screenshot': float(llm.get('browser_timeout_screenshot', 30.0) or 30.0),
        'browser_timeout_navigate': float(llm.get('browser_timeout_navigate', 30.0) or 30.0),
        'browser_headers': application.get('browser_headers', {}) if isinstance(application, dict) else {},
        'cdp_url': _effective_cdp_url(llm.get('browser_use_cdp_url', 'http://browser-stream:9222')),
        'max_steps': int(llm.get('browser_use_max_steps', 25) or 25),
        'use_vision': bool(llm.get('browser_use_vision', True)),
        'supervisor_enabled': bool(llm.get('supervisor_enabled', True)),
        'browser_agent_prompt': str(llm.get('browser_agent_prompt', '') or ''),
        'browser_provider': str(llm.get('browser_provider', 'playwright') or 'playwright'),
        'playwright_mcp_enabled': bool(llm.get('playwright_mcp_enabled', False)),
        'playwright_mcp_command': str(llm.get('playwright_mcp_command', 'npx') or 'npx'),
        'playwright_mcp_args': llm.get('playwright_mcp_args', ['-y', '@playwright/mcp@latest']),
    }


def _browser_use_available() -> bool:
    return all(item is not None for item in (Agent, BrowserSession, BrowserUseChatOpenAI))


def _build_browser_headers(runtime: dict[str, object], application_url: str) -> dict[str, str]:
    headers = {
        'X-Disney-Header-FNF-RIC-Uplift-Override': 'true',
        'x-Disney-internal-commerce-override-context': 'RACUI_ENABLED:true',
    }
    extra = runtime.get('browser_headers', {}) or {}
    if isinstance(extra, dict):
        headers.update({str(key): str(value) for key, value in extra.items() if key})
    if 'disney' in application_url.lower():
        headers.setdefault('X-Disney-Internal-conversationId', str(uuid4()))
        headers.setdefault('X-Disney-Internal-correlationId', str(uuid4()))
    return headers


def _build_browser_use_client(runtime: dict[str, object]):
    if not _browser_use_available():
        raise RuntimeError('browser_use dependencies are not installed')
    api_endpoint = str(runtime.get('api_endpoint', '') or '').rstrip('/')
    auth_token = str(runtime.get('auth_token', '') or '').strip()
    if not auth_token:
        raise RuntimeError('OpenAI API key is required for browser_use mode. Add it in Configuration Settings > AI / OpenAI Configuration > Auth Token or set OPENAI_API_KEY.')
    os.environ.setdefault('OPENAI_API_KEY', auth_token)
    browser_model = str(runtime.get('browser_model', 'gpt-4o-mini') or 'gpt-4o-mini')
    supervisor_model = str(runtime.get('supervisor_model', browser_model) or browser_model)
    common_kwargs = {'api_key': auth_token, 'temperature': float(runtime.get('temperature', 0.2) or 0.2)}
    if api_endpoint:
        common_kwargs['base_url'] = api_endpoint
        common_kwargs['default_headers'] = {'Authorization': f'Bearer {auth_token}', 'Content-Type': 'application/json'}
    browser_llm = BrowserUseChatOpenAI(model=browser_model, **common_kwargs)
    # browser-use releases differ on whether the OpenAI adapter exposes provider.
    # Keep the adapter compatible with versions that inspect llm.provider.
    if not getattr(browser_llm, 'provider', None):
        try:
            object.__setattr__(browser_llm, 'provider', 'openai')
        except Exception:
            pass
    supervisor_llm = None
    if LangChainChatOpenAI is not None:
        supervisor_llm = LangChainChatOpenAI(model=supervisor_model, **common_kwargs)
    return browser_llm, supervisor_llm


def _run_maybe_async(value):
    if inspect.isawaitable(value):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return asyncio.run(value)
        except RuntimeError:
            pass
        return asyncio.run(value)
    return value


def _build_llm_browser_task(application_url: str, objective: str, max_depth: int, max_pages: int, min_events: int) -> str:
    targets = _objective_targets(objective)
    target_text = ' -> '.join(targets) if targets else 'derive only from the stated objective and visible page evidence'
    return f"""
Control a real browser session for Journey AI.

Authoritative scope:
- Start URL: {application_url}
- Journey objective: {objective}
- Ordered objective targets: {target_text}
- Limits: max_depth={max_depth}, max_pages={max_pages}, minimum meaningful evidence events={min_events}

Execution contract:
1. The journey objective is the source of truth. Domain guidance is optional and must never redirect the run to a familiar but unrelated workflow.
2. Navigate to the exact start URL and wait for visible rendering. Inspect the DOM and accessibility state before every action.
3. Match controls using visible text, accessible name, role, id, selector, href, and destination semantics. Do not select a merely similar control when an explicit target is missing.
4. For hidden navigation, hover the objective-relevant parent, wait for rendering, rescan, and click only the matching child target.
5. Stay in objective order. Record every attempted target as succeeded, blocked, safety-skipped, or not found, with supporting URL and element evidence.
6. Do not create, delete, purchase, submit irreversible forms, log out, or modify production data unless the objective explicitly requires the action and the configured safety boundary permits it.
7. Stop only when every explicit target has a disposition, authentication or authorization blocks progress, or the crawl limits are reached.

Completion response:
Return a concise structured summary containing objective_status, matched_targets, missing_targets, pages_visited, actions_performed, clicked element labels/selectors, source and destination URLs, blocked reasons, and evidence gaps. Never report success for a different destination or workflow.
""".strip()

def _browser_use_to_journey(exploration_text: str, application_url: str, runtime: dict[str, object], parameters: dict[str, str], max_depth: int, max_pages: int, follow_links: bool, objective: str) -> ExplorationResult:
    browser_llm, supervisor_llm = _build_browser_use_client(runtime)
    headers = _build_browser_headers(runtime, application_url)
    profile_prompt = get_browser_agent_profile(application_url, objective)
    configured_prompt = str(runtime.get('browser_agent_prompt', '') or '').strip()
    if configured_prompt:
        profile_prompt = profile_prompt + '\n\nOptional configured guidance (lower priority than the journey objective; ignore conflicts):\n' + configured_prompt

    task = _build_llm_browser_task(application_url, objective, max_depth, max_pages, int(runtime.get('min_events', 10) or 10))
    cdp_url = _effective_cdp_url(runtime.get('cdp_url', 'http://browser-stream:9222'))
    browser_session = BrowserSession(cdp_url=cdp_url, headers=headers, keep_alive=True, wait_between_actions=0.6)
    agent = Agent(
        task=task,
        llm=browser_llm,
        sensitive_data=parameters,
        extend_system_message=profile_prompt,
        use_vision=bool(runtime.get('use_vision', True)),
        calculate_cost=True,
        browser_session=browser_session,
    )

    try:
        publish_event(application_url, {'type': 'llm_agent_started', 'status': 'LLM browser agent started', 'url': application_url, 'objective': objective, 'model': runtime.get('browser_model')})
        result = _run_maybe_async(agent.run(max_steps=int(runtime.get('max_steps', 25) or 25)))
        final_text = getattr(result, 'final_result', None) or getattr(result, 'content', None) or str(result)
        publish_event(application_url, {'type': 'llm_agent_completed', 'status': 'LLM browser agent completed', 'url': application_url, 'summary': final_text[:1200]})
    except Exception as exc:
        final_text = f'LLM browser agent failed: {type(exc).__name__}: {exc}'
        publish_event(application_url, {'type': 'llm_agent_failed', 'status': 'LLM browser agent failed', 'url': application_url, 'result': final_text})

    supervisor_text = ''
    if runtime.get('supervisor_enabled', True) and HumanMessage is not None and supervisor_llm is not None:
        try:
            prompt = profile_prompt + '\n\nSupervisor review contract:\nTreat the journey objective as authoritative. Compare each explicit target with the run output. Return: objective_status (achieved|partial|blocked), matched_targets, missing_targets, unsupported_actions, evidence_gaps, and recommended_next_action. Do not approve a familiar domain flow when it differs from the objective.\n\nJourney objective:\n' + objective + '\n\nRun output:\n' + final_text
            review = supervisor_llm.invoke([HumanMessage(content=prompt)])
            supervisor_text = str(getattr(review, 'content', review))
        except Exception as exc:
            supervisor_text = f'Supervisor unavailable: {type(exc).__name__}: {exc}'

    # Browser-use drives the session; Playwright captures authoritative DOM, screenshots, network, hover, and replay evidence for the UI.
    steps, crawl_reasoning, _ = _crawl_with_playwright(application_url, parameters, max_depth=max_depth, max_pages=max_pages, follow_links=follow_links, objective=objective, min_events=int(runtime.get('min_events', 10) or 10))
    return _build_browser_use_result(final_text + ('\n\nSupervisor review:\n' + supervisor_text if supervisor_text else ''), application_url, runtime, steps, crawl_reasoning, objective)

class _SimplePageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ''
        self._in_title = False
        self._heading_tag = ''
        self.headings: list[str] = []
        self.buttons: list[str] = []
        self.links: list[str] = []
        self.inputs: list[str] = []
        self.menus: list[str] = []
        self.sections: list[str] = []
        self._text_buffer: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'title':
            self._in_title = True
        elif tag in ('h1', 'h2', 'h3'):
            self._heading_tag = tag
            self._text_buffer = []
        elif tag == 'button' or attrs.get('role') == 'button':
            self._text_buffer = []
        elif tag in ('nav', 'menu'):
            self._text_buffer = []
        elif tag in ('section', 'main', 'article'):
            self._text_buffer = []
        elif tag == 'a' and attrs.get('href'):
            self._text_buffer = []
            self.links.append(_safe_text(attrs.get('href')))
        elif tag in ('input', 'select', 'textarea'):
            self.inputs.append(_safe_text(attrs.get('name') or attrs.get('placeholder') or attrs.get('aria-label') or attrs.get('id') or attrs.get('type') or 'control'))

    def handle_data(self, data):
        text = _safe_text(data)
        if not text:
            return
        if self._in_title:
            self.title += text
        self._text_buffer.append(text)

    def handle_endtag(self, tag):
        if tag == 'title':
            self._in_title = False
        elif tag in ('h1', 'h2', 'h3') and self._heading_tag == tag:
            text = _safe_text(' '.join(self._text_buffer))
            if text:
                self.headings.append(text)
            self._heading_tag = ''
            self._text_buffer = []
        elif tag == 'button':
            text = _safe_text(' '.join(self._text_buffer))
            if text:
                self.buttons.append(text)
            self._text_buffer = []
        elif tag in ('nav', 'menu'):
            text = _safe_text(' '.join(self._text_buffer))
            if text:
                self.menus.append(text)
            self._text_buffer = []
        elif tag in ('section', 'main', 'article'):
            text = _safe_text(' '.join(self._text_buffer))
            if text:
                self.sections.append(text[:120])
            self._text_buffer = []


def _safe_text(value: object) -> str:
    if value is None:
        return ''
    return str(value).strip()


def _same_origin(base_url: str, candidate_url: str) -> bool:
    base = urlparse(base_url)
    candidate = urlparse(candidate_url)
    return (base.scheme, base.netloc) == (candidate.scheme, candidate.netloc)


def _extract_title(page_url: str, title: str | None) -> str:
    if title and title.strip():
        return title.strip()
    parsed = urlparse(page_url)
    path = parsed.path.strip('/')
    if path:
        return path.split('/')[-1].replace('-', ' ').replace('_', ' ').title()
    return 'Home'


def _extract_page_signals(page) -> dict[str, object]:
    return page.evaluate(
        """() => {
          const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
          const headings = Array.from(document.querySelectorAll('h1, h2, h3')).slice(0, 100).map((el) => clean(el.textContent));
          const buttons = Array.from(document.querySelectorAll('button, [role="button"], input[type="submit"], input[type="button"]')).slice(0, 200).map((el) => clean(el.innerText || el.textContent || el.value || el.getAttribute('aria-label')));
          const links = Array.from(document.querySelectorAll('a[href]')).slice(0, 500).map((el) => clean(el.innerText || el.textContent));
          const inputs = Array.from(document.querySelectorAll('input, select, textarea')).slice(0, 100).map((el) => clean(el.getAttribute('name') || el.getAttribute('placeholder') || el.getAttribute('aria-label') || el.id || el.type || 'control'));
          const menus = Array.from(document.querySelectorAll('nav, menu')).slice(0, 20).map((el) => clean(el.innerText || el.textContent));
          const sections = Array.from(document.querySelectorAll('main, section, article')).slice(0, 100).map((el) => clean(el.innerText || el.textContent).slice(0, 120));
          const forms = Array.from(document.querySelectorAll('form')).slice(0, 50).map((form) => ({
            action: clean(form.getAttribute('action')),
            method: clean(form.getAttribute('method')),
            labels: Array.from(form.querySelectorAll('label')).slice(0, 8).map((label) => clean(label.textContent)),
          }));
          const primaryCta = buttons.find((text) => /start|continue|submit|sign in|log in|next|create|save|search|buy|checkout|explore/i.test(text)) || buttons[0] || '';
          return { headings, buttons, links, inputs, menus, sections, forms, primaryCta, title: document.title || '' };
        }
        """
    )


def _extract_clickable_actions(page) -> list[ClickCandidate]:
    raw = page.evaluate(
        """() => {
          const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
          const cssString = (value) => {
            try { return CSS.escape(value || ''); } catch (_) { return String(value || '').replace(/"/g, '\\"'); }
          };
          const selectorFor = (el) => {
            const tag = (el.tagName || '').toLowerCase();
            const id = clean(el.id || '');
            const aria = clean(el.getAttribute('aria-label') || '');
            const dataTest = clean(el.getAttribute('data-testid') || el.getAttribute('data-test') || '');
            const name = clean(el.getAttribute('name') || '');
            const href = clean(el.getAttribute('href') || '');
            if (id) return `#${cssString(id)}`;
            if (dataTest) return `[data-testid="${dataTest}"]`;
            if (aria) return `${tag || '*'}[aria-label="${aria}"]`;
            if (name) return `${tag || '*'}[name="${name}"]`;
            if (tag === 'a' && href) return `a[href="${href}"]`;
            return tag || '*';
          };
          const isVisible = (el) => {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || '1') > 0.05;
          };
          const elements = Array.from(document.querySelectorAll('a[href], button, [role="button"], [role="menuitem"], [role="tab"], input:not([type="password"]):not([type="file"]), select, textarea, summary'));
          return elements.map((el, index) => {
            const rect = el.getBoundingClientRect();
            const disabled = Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true');
            const text = clean(el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('title') || el.value || '');
            return {
              index,
              text,
              href: clean(el.href || el.getAttribute('href') || ''),
              tag: (el.tagName || '').toLowerCase(),
              role: clean(el.getAttribute('role') || ''),
              element_id: clean(el.id || ''),
              selector: selectorFor(el),
              value: clean(el.value || el.getAttribute('aria-label') || ''),
              input_type: clean(el.getAttribute('type') || ''),
              visible: isVisible(el),
              disabled,
              area: Math.round(rect.width * rect.height),
            };
          }).filter((item) => item.visible && !item.disabled && (item.text || item.href)).slice(0, 500);
        }
        """
    )
    allowed_keys = set(ClickCandidate.__dataclass_fields__.keys())
    return [ClickCandidate(**{key: value for key, value in item.items() if key in allowed_keys}) for item in raw]


def _resolve_href(base_url: str, href: str) -> str:
    return urljoin(base_url, href)


def _looks_like_safe_cta(text: str, tag: str = '') -> bool:
    return bool(text) and bool(re.search(
        r'start|continue|next|learn more|view|open|details|explore|sign in|log in|create|register|search|submit|buy|checkout|select|'
        r'preferences?|workspace|report lookup|lookup|reports?|settings?|manage|projects?',
        text,
        re.I,
    ))


def _normalize_match_text(value: object) -> str:
    text = str(value or '').lower().replace('&', ' and ')
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _requires_full_page_inventory(objective: str) -> bool:
    normalized = _normalize_match_text(objective)
    return any(phrase in normalized for phrase in (
        'discover the primary user journey from the application home page',
        'explore the home page',
        'explore the homepage',
        'complete homepage',
        'complete home page',
        'full page',
        'complete page',
        'scroll through the complete page',
        'scroll to the bottom',
        'scroll from top to bottom',
        'all visible cards',
        'all cards',
        'all links',
        'all inventories',
        'complete inventory',
    ))


def _objective_limits_to_current_page(objective: str) -> bool:
    normalized = _normalize_match_text(objective)
    return any(phrase in normalized for phrase in (
        'home page only',
        'homepage only',
        'current page only',
        'do not open links',
        'without opening links',
        'do not navigate away',
    ))


def _generic_internal_link_candidates(actions: list[ClickCandidate], application_url: str, current_url: str, objective: str, limit: int = 50) -> list[ClickCandidate]:
    selected: list[ClickCandidate] = []
    seen_urls: set[str] = set()
    for candidate in actions:
        if candidate.tag != 'a' or not candidate.href:
            continue
        target_url = _resolve_href(current_url or application_url, candidate.href)
        parsed = urlparse(target_url)
        normalized_target = target_url.split('#', 1)[0].rstrip('/')
        normalized_current = (current_url or application_url).split('#', 1)[0].rstrip('/')
        if (
            parsed.scheme not in {'http', 'https'}
            or not _same_origin(application_url, target_url)
            or normalized_target == normalized_current
            or normalized_target in seen_urls
            or not _is_safe_observation_click(candidate.text or candidate.value, candidate.tag, objective)
        ):
            continue
        seen_urls.add(normalized_target)
        selected.append(candidate)
        if len(selected) >= limit:
            break
    return selected

def _objective_action_targets(objective: str) -> list[tuple[str, str]]:
    raw = re.sub(r'https?://\S+', ' ', objective or '')
    action_pattern = re.compile(
        r'\b(?P<action>hover(?:ing)?(?:\s+(?:over|on))?|mouse\s+over|point\s+to|move\s+(?:the\s+)?(?:mouse|cursor|pointer)\s+(?:over|to)|click(?:ing)?(?:\s+on)?|select(?:ing)?|activate(?:ing)?)'
        r'\s+(?:the\s+)?(?P<label>.+?)'
        r'(?=\s+without\s+clicking\b|\s+(?:and\s+)?(?:wait|then|click|select|activate|open|inspect|verify|capture|explore)\b|[,.;:\n]|$)',
        re.I,
    )
    targets: list[tuple[str, str]] = []
    for match in action_pattern.finditer(raw):
        action_text = _normalize_match_text(match.group('action'))
        action = 'hover' if any(word in action_text for word in ('hover', 'mouse', 'cursor', 'pointer', 'point')) else 'click'
        label = re.sub(r'[`*_#]+', ' ', match.group('label'))
        label = re.sub(
            r'\s+(?:in|under|inside|from)\s+(?:the\s+)?(?:main\s+)?(?:navigation|navbar|nav|sidebar|header|menu)\b.*$',
            '',
            label,
            flags=re.I,
        )
        label = re.sub(r'\s+(?:link|item|control|tab|button)\s*$', '', label, flags=re.I)
        label = re.sub(r'\s+(?:exactly\s+)?once\s*$', '', label, flags=re.I)
        normalized_label = _normalize_match_text(label)
        if normalized_label in {'tickets and parks', 'tickets parks'}:
            normalized_label = 'tickets parks'
        if normalized_label == 'workspaces':
            normalized_label = 'workspace'
        if normalized_label == 'preference':
            normalized_label = 'preferences'
        if normalized_label and (action, normalized_label) not in targets:
            targets.append((action, normalized_label))
    return targets

def _objective_targets(objective: str) -> list[str]:
    """Return ordered, actionable labels from a natural-language objective."""
    raw = objective or ''
    normalized = _normalize_match_text(re.sub(r'https?://\S+', ' ', raw))
    if 'plan your visit' in normalized and ('tickets and parks' in normalized or 'tickets parks' in normalized):
        return ['tickets parks', 'ticket buying guide', '3 step planning guide', 'lightning lane passes', 'maps', 'transportation']

    known_phrases = [
        'accept all',
        'allow all',
        'accept cookies',
        'data and ai',
        'cloud data engineering',
        'functional expertise',
        'industries',
        'knowledge hub',
        'company',
        'contact',
        'tickets and parks',
        'tickets parks',
        'view special offers',
        'special offers',
        'preference',
        'preferences',
        'workspace',
        'workspaces',
        'report lookup',
        'schema analyzer',
        'projects',
    ]
    phrase_hits: list[tuple[int, str]] = []
    for phrase in known_phrases:
        index = normalized.find(_normalize_match_text(phrase))
        if index >= 0:
            label = 'tickets parks' if phrase in {'tickets and parks', 'tickets parks'} else phrase
            label = 'workspace' if phrase == 'workspaces' else label
            label = 'preferences' if phrase == 'preference' else label
            phrase_hits.append((index, label))
    ordered_phrases: list[str] = []
    for _, phrase in sorted(phrase_hits, key=lambda item: item[0]):
        if phrase not in ordered_phrases:
            ordered_phrases.append(phrase)

    explicit_action_targets = _objective_action_targets(raw)
    if any(action == 'hover' for action, _ in explicit_action_targets):
        action_labels = [label for _, label in explicit_action_targets]
        consent_targets = [phrase for phrase in ordered_phrases if _is_consent_objective_target(phrase)]
        ordered_targets: list[str] = []
        for label in consent_targets + action_labels + ordered_phrases:
            if not any(label == existing or label in existing or existing in label for existing in ordered_targets):
                ordered_targets.append(label)
        return ordered_targets
    if 'data and ai' in ordered_phrases and 'cloud data engineering' in ordered_phrases:
        consent_targets = [phrase for phrase in ordered_phrases if _is_consent_objective_target(phrase)]
        required_path = consent_targets + ['data and ai', 'cloud data engineering']
        return required_path + [phrase for phrase in ordered_phrases if phrase not in required_path]

    # Natural-language objectives may introduce the child before describing
    # the menu interaction. Prefer explicit hover-parent/click-child order
    # when present, while leaving ordinary objective parsing unchanged.
    explicit_order: list[str] = []
    hover_match = re.search(r'hover(?: over)?\s+(.*?)(?=\s+(?:in|on|until)\b|\s+and\s+(?:wait|then|click)\b)', normalized)
    click_match = re.search(r'(?:locate and )?click\s+(.*?)(?=\s+(?:under|in|on|after|and)\b|$)', normalized)
    for match in (hover_match, click_match):
        fragment = match.group(1) if match else ''
        matching_phrases = [
            phrase for phrase in ordered_phrases
            if _normalize_match_text(phrase) in fragment or all(word in fragment.split() for word in _normalize_match_text(phrase).split())
        ]
        if matching_phrases:
            phrase = max(matching_phrases, key=len)
            if phrase not in explicit_order:
                explicit_order.append(phrase)
    if explicit_order:
        return explicit_order + [phrase for phrase in ordered_phrases if phrase not in explicit_order]
    if ordered_phrases:
        return ordered_phrases
    stop_words = {
        'a', 'an', 'and', 'are', 'at', 'be', 'by', 'capture', 'click', 'collect', 'details',
        'do', 'each', 'for', 'from', 'get', 'give', 'in', 'inside', 'into', 'of', 'on', 'open',
        'page', 'record', 'select', 'starting', 'stop', 'the', 'then', 'to', 'user', 'using',
        'with', 'without', 'journey', 'explore', 'exploration', 'available', 'relevant',
        'options', 'structure', 'controls', 'inputs', 'dropdowns', 'navigation', 'every',
    }
    tokens = [token for token in re.findall(r'[a-z0-9]+', normalized) if token not in stop_words and len(token) > 2]
    targets: list[str] = []
    for index, token in enumerate(tokens):
        if index + 1 < len(tokens) and token in {'report', 'workspace', 'special'} and tokens[index + 1] in {'lookup', 'details', 'names', 'offers'}:
            phrase = f'{token} {tokens[index + 1]}'
            if phrase not in targets:
                targets.append(phrase)
        elif token not in targets and token not in {'names', 'name', 'page', 'report'}:
            targets.append(token)
    return targets


def _objective_match_score(candidate: ClickCandidate, objective: str) -> tuple[int, int]:
    text = _normalize_match_text(f'{candidate.text} {candidate.href} {candidate.value} {candidate.role} {candidate.element_id}')
    targets = _objective_targets(objective)
    for position, target in enumerate(targets):
        target_text = _normalize_match_text(target)
        if target_text and target_text in text:
            return 1000 - position * 10, position
        words = target_text.split()
        if words and sum(word in text for word in words) == len(words):
            return 800 - position * 10, position
    return 0, len(targets)
def _derive_page_name(page_url: str, title: str | None = None) -> str:
    if title and title.strip():
        return title.strip()
    parsed = urlparse(page_url)
    slug = (parsed.path.strip('/').split('/')[-1] or parsed.netloc).replace('-', ' ').replace('_', ' ')
    return slug.title() if slug else 'Home'


def _build_interaction(
    *,
    sequence_id: int,
    interaction_number: int,
    page_url: str,
    element_type: str,
    element_label: str,
    element_id: str | None = None,
    role: str = '',
    selector: str,
    action: str,
    value: str | None,
    state_before: str | None,
    state_after: str | None,
    resulted_in: str,
    wait_condition: str,
    expected_text: str | None = None,
    validation_message: str | None = None,
    api_call_triggered: str | None = None,
    api_method: str | None = None,
    api_response_status: int | str | None = None,
    is_dynamic_element: bool = False,
    is_custom_component: bool = False,
    is_shadow_dom: bool = False,
    iframe_context: str | None = None,
    parent_component: str = '',
    event_timestamp: str = '',
    screenshot_before: str | None = None,
    screenshot_after: str | None = None,
    destination_url: str | None = None,
    coordinates: dict[str, float] | None = None,
    network_events: list[dict[str, object]] | None = None,
    dom_snapshot_before: str | None = None,
    dom_snapshot_after: str | None = None,
    iframe_inventory: list[dict[str, object]] | None = None,
    popup_activity: list[dict[str, object]] | None = None,
    visible_elements: list[dict[str, object]] | None = None,
    replay: dict[str, object] | None = None,
    min_length: str | int | None = None,
    max_length: str | int | None = None,
) -> Interaction:
    return Interaction(
        sequence_id=sequence_id,
        interaction_number=interaction_number,
        element_type=element_type,
        element_label=element_label,
        element_id=element_id,
        role=role,
        selector=selector,
        selector_type='css' if selector else '',
        action=action,
        value=value,
        page_url=page_url,
        element_state_before=state_before,
        element_state_after=state_after,
        resulted_in=resulted_in,
        wait_condition=wait_condition,
        min_length=min_length,
        max_length=max_length,
        expected_text=expected_text,
        validation_message=validation_message,
        api_call_triggered=api_call_triggered,
        api_method=api_method,
        api_response_status=api_response_status,
        is_dynamic_element=is_dynamic_element,
        is_custom_component=is_custom_component,
        is_shadow_dom=is_shadow_dom,
        iframe_context=iframe_context,
        parent_component=parent_component,
        event_timestamp=event_timestamp,
        screenshot_before=screenshot_before,
        screenshot_after=screenshot_after,
        destination_url=destination_url,
        coordinates=coordinates or {},
        network_events=network_events or [],
        dom_snapshot_before=dom_snapshot_before,
        dom_snapshot_after=dom_snapshot_after,
        iframe_inventory=iframe_inventory or [],
        popup_activity=popup_activity or [],
        visible_elements=visible_elements or [],
        replay=replay or {},
    )


def _build_step(step_number: int, depth_level: int, page_title: str, page_url: str, interactions: list[Interaction]) -> JourneyStep:
    return JourneyStep(step_number=step_number, depth_level=depth_level, page_title=page_title, page_url=page_url, interactions=interactions)

def _enrich_capture_identity(steps: list[JourneyStep], journey_id: str) -> list[JourneyStep]:
    enriched: list[JourneyStep] = []
    for step in steps:
        page_key = f'{journey_id}:{step.page_url}:{step.step_number}'
        page_id = 'PAGE-' + hashlib.sha1(page_key.encode('utf-8')).hexdigest()[:12]
        route = urlparse(step.page_url).path or '/'
        events: list[Interaction] = []
        for position, interaction in enumerate(step.interactions, start=1):
            before = interaction.dom_snapshot_before or ''
            after = interaction.dom_snapshot_after or ''
            visible = [{
                'type': interaction.element_type,
                'label': interaction.element_label,
                'selector': interaction.selector,
                'role': interaction.role,
                'visible': True,
            }] if interaction.element_type not in {'page', 'scan'} else []
            event_key = f'{journey_id}:{page_id}:{interaction.sequence_id or position}'
            events.append(interaction.model_copy(update={
                'event_id': 'EVT-' + hashlib.sha1(event_key.encode('utf-8')).hexdigest()[:12],
                'page_id': page_id,
                'route': route,
                'state_fingerprint_before': hashlib.sha256(before.encode('utf-8')).hexdigest()[:16] if before else '',
                'state_fingerprint_after': hashlib.sha256(after.encode('utf-8')).hexdigest()[:16] if after else '',
                'visible_elements': visible,
            }))
        enriched.append(step.model_copy(update={'interactions': events}))
    return enriched



def _build_journey_record(*, journey_id: str, title: str, starting_url: str, outcome: str, outcome_detail: str, reasoning: str, total_depth: int, test_hints: dict[str, object], steps: list[JourneyStep], boundary_reached: bool = False, boundary_url: str | None = None) -> JourneyRecord:
    return JourneyRecord(
        journey_id=journey_id,
        journey_title=title,
        starting_point=_extract_title(starting_url, None),
        starting_url=starting_url,
        outcome=outcome,
        outcome_detail=outcome_detail,
        reasoning=reasoning,
        session_boundary_reached=boundary_reached,
        session_boundary_url=boundary_url,
        total_depth=total_depth,
        test_hints=test_hints,
        housekeeping_steps=[],
        steps=steps,
    )


def _build_url_specific_fallback(application_url: str, parameters: dict[str, str]) -> tuple[list[JourneyStep], list[str], list[str]]:
    page_name = _extract_title(application_url, None)
    interactions = [
        _build_interaction(
            sequence_id=1,
            interaction_number=1,
            page_url=application_url,
            element_type='page',
            element_label=page_name,
            selector=application_url,
            action='open',
            value=None,
            state_before='unknown',
            state_after='loaded',
            resulted_in='page_load',
            wait_condition='domcontentloaded',
            parent_component='landing_page',
        )
    ]
    step = _build_step(1, 0, page_name, application_url, interactions)
    return [step], [f'Loaded {application_url}'], [f'Open landing page at {application_url}']


def _should_hover_target(candidate: ClickCandidate, objective: str, current_target: str, next_target: str, visible_actions: list[ClickCandidate]) -> bool:
    if _objective_requires_hover(objective, current_target, candidate):
        return True
    return bool(
        next_target
        and not _target_visible_in_actions(visible_actions, next_target)
        and _can_hover_candidate(candidate)
    )

def _score_candidate(candidate: ClickCandidate, profile_text: str, objective: str = '') -> int:
    text = (candidate.text or '').lower()
    href = (candidate.href or '').lower()
    score, _ = _objective_match_score(candidate, objective)
    if _looks_like_safe_cta(text):
        score += 30
    if not objective.strip() and any(keyword in text for keyword in ('buy', 'ticket', 'park', 'guest', 'checkout', 'continue', 'search', 'manage', 'invite', 'add a guest', 'create managed profile', 'theme park', 'admission')):
        score += 25
    if not objective.strip() and any(keyword in profile_text for keyword in ('disney', 'ticket', 'park', 'guest', 'family', 'friends')) and any(keyword in text for keyword in ('ticket', 'park', 'guest', 'invite', 'profile', 'checkout', 'add', 'admission')):
        score += 25
    if candidate.tag == 'button':
        score += 10
    elif candidate.tag == 'a':
        score += 5
    if href and href.startswith('#'):
        score -= 10
    if any(keyword in text for keyword in ('cookie', 'privacy', 'terms', 'help', 'support', 'policy')):
        score -= 20
    if len(text) > 80:
        score -= 5
    return score


def _choose_objective_actions(actions: list[ClickCandidate], profile_text: str, objective: str, target_index: int = 0) -> list[ClickCandidate]:
    """Choose the next objective control instead of clicking unrelated page controls."""
    targets = _objective_targets(objective)
    target = targets[target_index] if target_index < len(targets) else ''
    def target_score(action: ClickCandidate) -> int:
        if not target:
            return 0
        candidate_text = _normalize_match_text(f'{action.text} {action.href} {action.value} {action.role} {action.element_id}')
        target_text = _normalize_match_text(target)
        if target_text and target_text in candidate_text:
            return 1000
        words = target_text.split()
        return 800 if words and all(word in candidate_text for word in words) else 0

    ranked = sorted(
        ((target_score(action), _score_candidate(action, profile_text, objective), action) for action in actions),
        key=lambda item: (item[0], item[1]),
        reverse=True,
    )
    objective_matches = [item[2] for item in ranked if item[0] > 0]
    if objective_matches:
        return objective_matches[:1]
    if target:
        return []
    safe = [action for action in sorted(actions, key=lambda action: _score_candidate(action, profile_text, objective), reverse=True) if _is_safe_observation_click(action.text or action.value, action.tag, objective)]
    return safe[:3]

def _target_visible_in_actions(actions: list[ClickCandidate], target: str) -> bool:
    return any(_objective_match_score(action, target)[0] > 0 for action in actions)


def _is_consent_objective_target(target: str) -> bool:
    return _normalize_match_text(target) in {'accept all', 'allow all', 'accept cookies'}


def _objective_explicitly_targets_action(objective: str, target: str, candidate: ClickCandidate | None, action: str) -> bool:
    normalized = _normalize_match_text(objective)
    labels = {
        _normalize_match_text(target),
        _normalize_match_text(candidate.text if candidate else ''),
        _normalize_match_text(candidate.value if candidate else ''),
    }
    labels.discard('')
    if action == 'hover':
        verb = r'(?:hover(?:ing)?(?:\s+(?:over|on))?|mouse\s+over|point\s+to|move\s+(?:the\s+)?(?:mouse|cursor|pointer)\s+(?:over|to))'
    else:
        verb = r'(?:click(?:ing)?(?:\s+on)?|select(?:ing)?|activate(?:ing)?)'
    for label in labels:
        label_pattern = r'\s+'.join(re.escape(word) for word in label.split())
        pattern = re.compile(rf'\b{verb}\s+(?:the\s+)?{label_pattern}\b')
        for match in pattern.finditer(normalized):
            prefix = normalized[max(0, match.start() - 24):match.start()]
            if not re.search(r'(?:do\s+not|dont|never|without)\s*$', prefix):
                return True
    return False


def _objective_requires_hover(objective: str, target: str, candidate: ClickCandidate | None = None) -> bool:
    return _objective_explicitly_targets_action(objective, target, candidate, 'hover')


def _objective_explicitly_clicks_target(objective: str, target: str, candidate: ClickCandidate | None = None) -> bool:
    return _objective_explicitly_targets_action(objective, target, candidate, 'click')

def _can_hover_candidate(candidate: ClickCandidate) -> bool:
    label = _normalize_match_text(candidate.text or candidate.value or candidate.href)
    return (
        candidate.tag == 'summary'
        or candidate.role in {'menuitem', 'tab'}
        or bool(re.search(
            r'menu|navigation|tickets? parks?|data and ai|functional expertise|industries|knowledge hub|company|preference|workspace|report|offer',
            label,
            re.I,
        ))
    )

def _page_to_step(page_number: int, depth: int, page_url: str, title: str, signals: dict[str, object], interactions: list[Interaction]) -> JourneyStep:
    page_title = _safe_text(title) or _derive_page_name(page_url, title)
    return _build_step(page_number, depth, page_title, page_url, interactions)


def _is_safe_observation_click(text: str, tag: str, objective: str = '') -> bool:
    text = text or ''
    normalized_text = _normalize_match_text(text)
    normalized_objective = _normalize_match_text(objective)
    consent_action = normalized_text in {'accept all', 'allow all', 'accept cookies'}
    consent_authorized = any(phrase in normalized_objective for phrase in ('accept all', 'allow all', 'accept cookies'))
    if consent_action:
        return consent_authorized
    if re.search(r'buy|purchase|checkout|delete|remove|logout|sign out|submit|create account|password', text, re.I):
        return False
    if tag in {'input', 'select', 'textarea', 'summary'}:
        return True
    if tag == 'a' and text:
        return True
    return bool(re.search(r'menu|filter|details|learn more|view|open|expand|show|hide|tickets|parks|offers|search|explore|continue|next|preferences?|workspace|report lookup|lookup|settings?|manage|projects?', text, re.I))


def _wait_for_page_ready(page, timeout_ms: int = 15000, settle_ms: int = 700) -> str:
    """Wait for navigation and SPA rendering before inspecting or interacting."""
    conditions = []
    try:
        page.wait_for_load_state('domcontentloaded', timeout=timeout_ms)
        conditions.append('domcontentloaded')
    except Exception:
        conditions.append('domcontentloaded_timeout')
    try:
        page.wait_for_load_state('networkidle', timeout=min(timeout_ms, 5000))
        conditions.append('networkidle')
    except Exception:
        conditions.append('networkidle_timeout')
    try:
        page.wait_for_function("document.readyState === 'complete'", timeout=3000)
        conditions.append('document_complete')
    except Exception:
        conditions.append('document_complete_timeout')
    page.wait_for_timeout(settle_ms)
    conditions.append('render_settled')
    return '+'.join(conditions)



def _capture_dom_snapshot(page, limit: int = 500000) -> str:
    """Best-effort DOM snapshot for evidence; never block the journey if capture fails."""
    try:
        snapshot = page.evaluate("""() => {
          const clone = document.documentElement.cloneNode(true);
          clone.querySelectorAll('[data-browser-agent-overlay]').forEach((node) => node.remove());
          return '<!DOCTYPE html>' + clone.outerHTML;
        }""")
        return str(snapshot or '')[:limit]
    except Exception:
        try:
            return page.content()[:limit]
        except Exception:
            return ''


def _capture_viewport_screenshot(page, prefix: str) -> str:
    """Best-effort screenshot capture for page-level evidence."""
    try:
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        path = GENERATED_DIR / f'{unique_filename(prefix, "")}.png'
        page.screenshot(path=str(path), full_page=False)
        return str(path)
    except Exception:
        return ''
def _signal_preview_items(signals: dict[str, object], limit: int = 8) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for group in ('headings', 'buttons', 'links', 'inputs', 'menus', 'sections'):
        values = signals.get(group, []) or []
        for value in values[:limit]:
            if isinstance(value, dict):
                label = value.get('label') or value.get('text') or value.get('name') or str(value)
            else:
                label = str(value)
            label = _safe_text(label)
            if label:
                items.append({'type': group[:-1], 'label': label[:180]})
    return items[:limit * 3]


def _candidate_preview(candidate: ClickCandidate, score: int | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        'index': candidate.index,
        'text': candidate.text,
        'href': candidate.href,
        'tag': candidate.tag,
        'role': candidate.role,
        'element_id': candidate.element_id,
        'selector': candidate.selector,
        'value': candidate.value,
        'input_type': candidate.input_type,
    }
    if score is not None:
        payload['score'] = score
    return payload


def _publish_agent_event(stream_key: str, event: dict[str, object]) -> None:
    if stream_key:
        publish_event(stream_key, event)

def _install_live_page_observers(page, stream_key: str) -> list[tuple[str, object]]:
    """Mirror passive Playwright telemetry to the shared live SSE stream."""
    listeners: list[tuple[str, object]] = []
    response_count = {'value': 0}

    def on_frame_navigated(frame):
        if frame is not page.main_frame:
            return
        _publish_agent_event(stream_key, {'type': 'navigation_observed', 'status': 'Navigated', 'url': frame.url, 'title': page.title() if not page.is_closed() else '', 'source': 'playwright'})

    def on_response(response):
        resource_type = response.request.resource_type
        if resource_type not in {'document', 'xhr', 'fetch'} or response_count['value'] >= 80:
            return
        response_count['value'] += 1
        _publish_agent_event(stream_key, {'type': 'network_response', 'status': 'Network response', 'url': response.url, 'page_url': page.url, 'http_status': response.status, 'method': response.request.method, 'resource_type': resource_type, 'sequence': response_count['value'], 'source': 'playwright'})

    page.on('framenavigated', on_frame_navigated)
    page.on('response', on_response)
    listeners.extend([('framenavigated', on_frame_navigated), ('response', on_response)])
    return listeners


def _remove_live_page_observers(page, listeners: list[tuple[str, object]]) -> None:
    for event_name, listener in listeners:
        try:
            page.remove_listener(event_name, listener)
        except Exception:
            pass

def _build_inventory_interactions(actions: list[ClickCandidate], sequence: int, page_url: str, minimum_remaining: int, stream_key: str = '', dom_snapshot: str = '', screenshot_path: str = '') -> tuple[list[Interaction], int]:
    """Capture visible DOM controls as evidence without unsafe extra clicks."""
    interactions: list[Interaction] = []
    seen: set[str] = set()
    for candidate in actions:
        if len(interactions) >= minimum_remaining:
            break
        label = _safe_text(candidate.text or candidate.value or candidate.href or candidate.selector)
        if not label:
            continue
        key = f'{candidate.tag}:{candidate.selector}:{label}'.lower()
        if key in seen:
            continue
        seen.add(key)
        _publish_agent_event(stream_key, {
            'type': 'control_observed',
            'status': 'Observed',
            'url': page_url,
            'element': label,
            'tag': candidate.tag,
            'role': candidate.role,
            'selector': candidate.selector,
            'href': candidate.href,
            'sequence': sequence,
            'result': 'Visible control captured for journey evidence.',
        })
        interactions.append(_build_interaction(
            sequence_id=sequence,
            interaction_number=sequence,
            page_url=page_url,
            element_type=candidate.tag or 'control',
            element_label=label,
            element_id=candidate.element_id or None,
            role=candidate.role,
            selector=candidate.selector or candidate.href or label,
            action='inspect',
            value=candidate.value or None,
            state_before='visible',
            state_after='captured',
            resulted_in='visible_control_captured',
            wait_condition='none',
            destination_url=candidate.href or None,
            is_dynamic_element=True,
            is_custom_component=candidate.tag in {'button', 'select', 'input', 'textarea'},
            parent_component='dom_inventory',
            replay={'action': 'inspect', 'selector': candidate.selector or candidate.href or label, 'source_url': page_url},
            screenshot_after=screenshot_path or None,
            dom_snapshot_after=dom_snapshot or None,
        ))
        sequence += 1
    return interactions, sequence
def _capture_full_page_inventory(
    page,
    sequence: int,
    page_url: str,
    stream_key: str,
    *,
    return_to_top: bool = False,
    max_scrolls: int = 40,
    max_controls: int = 500,
    live_preview: bool = False,
) -> tuple[list[Interaction], int, list[ClickCandidate], dict[str, int]]:
    """Scroll through a rendered page and persist each newly visible control once."""
    interactions: list[Interaction] = []
    discovered: list[ClickCandidate] = []
    seen: set[str] = set()
    scroll_count = 0
    try:
        if live_preview:
            scroll_live_page(page, 0, 'Returning to page top')
        else:
            page.evaluate("() => window.scrollTo(0, 0)")
            page.wait_for_timeout(350)
    except Exception:
        pass

    for viewport_index in range(max_scrolls + 1):
        metrics = page.evaluate(
            """() => {
              const root = document.scrollingElement || document.documentElement;
              return {
                y: Math.round(root.scrollTop || window.scrollY || 0),
                viewport: Math.round(window.innerHeight || root.clientHeight || 0),
                height: Math.round(Math.max(root.scrollHeight || 0, document.body?.scrollHeight || 0)),
              };
            }"""
        )
        viewport_actions = _extract_clickable_actions(page)
        new_actions: list[ClickCandidate] = []
        for candidate in viewport_actions:
            key = _candidate_ledger_key(page_url, candidate)
            if key in seen or len(discovered) >= max_controls:
                continue
            seen.add(key)
            discovered.append(candidate)
            new_actions.append(candidate)

        viewport_screenshot = _capture_viewport_screenshot(page, f'page_{sequence}_viewport_{viewport_index + 1}')
        if new_actions:
            inventory_interactions, sequence = _build_inventory_interactions(
                new_actions,
                sequence,
                page_url,
                len(new_actions),
                stream_key,
                '',
                viewport_screenshot,
            )
            interactions.extend(inventory_interactions)

        current_y = int(metrics.get('y', 0) or 0)
        viewport_height = max(1, int(metrics.get('viewport', 0) or 0))
        document_height = max(viewport_height, int(metrics.get('height', 0) or 0))
        at_bottom = current_y + viewport_height >= document_height - 4
        if at_bottom:
            page.wait_for_timeout(900)
            refreshed_height = int(page.evaluate("() => Math.max((document.scrollingElement || document.documentElement).scrollHeight || 0, document.body?.scrollHeight || 0)") or document_height)
            if refreshed_height <= document_height + 2:
                break
            document_height = refreshed_height

        target_y = min(current_y + max(450, int(viewport_height * 0.82)), max(0, document_height - viewport_height))
        if target_y <= current_y:
            break
        before_screenshot = viewport_screenshot
        if live_preview:
            scroll_live_page(page, target_y, f'Scrolling to viewport {viewport_index + 2}')
        else:
            page.evaluate("(targetY) => window.scrollTo({ top: targetY, behavior: 'auto' })", target_y)
            page.wait_for_timeout(750)
        after_metrics = page.evaluate(
            """() => {
              const root = document.scrollingElement || document.documentElement;
              return {
                y: Math.round(root.scrollTop || window.scrollY || 0),
                viewport: Math.round(window.innerHeight || root.clientHeight || 0),
                height: Math.round(Math.max(root.scrollHeight || 0, document.body?.scrollHeight || 0)),
              };
            }"""
        )
        after_screenshot = _capture_viewport_screenshot(page, f'page_{sequence}_scroll_{viewport_index + 1}')
        scroll_count += 1
        _publish_agent_event(stream_key, {
            'type': 'scroll_completed',
            'status': 'Scrolled',
            'url': page_url,
            'sequence': sequence,
            'scroll_number': scroll_count,
            'from_y': current_y,
            'to_y': int(after_metrics.get('y', target_y) or target_y),
            'document_height': int(after_metrics.get('height', document_height) or document_height),
            'new_controls': len(new_actions),
            'screenshot_after': after_screenshot,
        })
        interactions.append(_build_interaction(
            sequence_id=sequence,
            interaction_number=sequence,
            page_url=page_url,
            element_type='page',
            element_label=f'Page scroll {scroll_count}',
            selector='document.scrollingElement',
            action='scroll',
            value=str(int(after_metrics.get('y', target_y) or target_y)),
            state_before=f'scroll_y:{current_y}',
            state_after=f"scroll_y:{int(after_metrics.get('y', target_y) or target_y)}",
            resulted_in=f'viewport_scanned:new_controls={len(new_actions)}',
            wait_condition='render_settled',
            coordinates={
                'x': 0.0,
                'y': float(after_metrics.get('y', target_y) or target_y),
                'width': 0.0,
                'height': float(after_metrics.get('viewport', viewport_height) or viewport_height),
            },
            event_timestamp=datetime.now(timezone.utc).isoformat(),
            screenshot_before=before_screenshot or None,
            screenshot_after=after_screenshot or None,
            replay={'action': 'scroll', 'selector': 'document.scrollingElement', 'value': str(target_y), 'source_url': page_url},
            parent_component='full_page_inventory',
        ))
        sequence += 1

    final_snapshot = _capture_dom_snapshot(page)
    final_screenshot = _capture_viewport_screenshot(page, f'page_{sequence}_full_inventory_complete')
    final_metrics = page.evaluate(
        """() => {
          const root = document.scrollingElement || document.documentElement;
          return {
            y: Math.round(root.scrollTop || window.scrollY || 0),
            viewport: Math.round(window.innerHeight || root.clientHeight || 0),
            height: Math.round(Math.max(root.scrollHeight || 0, document.body?.scrollHeight || 0)),
          };
        }"""
    )
    visible_elements = [
        {
            'type': candidate.tag or candidate.role or 'control',
            'label': candidate.text or candidate.value or candidate.href,
            'role': candidate.role,
            'selector': candidate.selector,
            'href': candidate.href,
        }
        for candidate in discovered
    ]
    _publish_agent_event(stream_key, {
        'type': 'full_page_inventory_completed',
        'status': 'Full page captured',
        'url': page_url,
        'sequence': sequence,
        'scroll_count': scroll_count,
        'control_count': len(discovered),
        'document_height': int(final_metrics.get('height', 0) or 0),
        'screenshot_after': final_screenshot,
        'dom_snapshot_captured': bool(final_snapshot),
    })
    interactions.append(_build_interaction(
        sequence_id=sequence,
        interaction_number=sequence,
        page_url=page_url,
        element_type='inventory',
        element_label='Full page inventory',
        selector='document',
        action='inspect',
        value=str(len(discovered)),
        state_before='top',
        state_after='bottom_reached',
        resulted_in=f'full_page_captured:scrolls={scroll_count};controls={len(discovered)}',
        wait_condition='document_height_stable',
        coordinates={
            'x': 0.0,
            'y': float(final_metrics.get('y', 0) or 0),
            'width': 0.0,
            'height': float(final_metrics.get('height', 0) or 0),
        },
        event_timestamp=datetime.now(timezone.utc).isoformat(),
        screenshot_after=final_screenshot or None,
        dom_snapshot_after=final_snapshot or None,
        visible_elements=visible_elements,
        replay={'action': 'inspect', 'selector': 'document', 'source_url': page_url},
        parent_component='full_page_inventory',
    ))
    sequence += 1

    if return_to_top and int(final_metrics.get('y', 0) or 0) > 0:
        if live_preview:
            scroll_live_page(page, 0, 'Returning to top for objective actions')
        else:
            page.evaluate("() => window.scrollTo(0, 0)")
            page.wait_for_timeout(500)
        top_screenshot = _capture_viewport_screenshot(page, f'page_{sequence}_returned_top')
        interactions.append(_build_interaction(
            sequence_id=sequence,
            interaction_number=sequence,
            page_url=page_url,
            element_type='page',
            element_label='Return to top for objective actions',
            selector='document.scrollingElement',
            action='scroll',
            value='0',
            state_before='bottom_reached',
            state_after='scroll_y:0',
            resulted_in='returned_to_top',
            wait_condition='render_settled',
            event_timestamp=datetime.now(timezone.utc).isoformat(),
            screenshot_before=final_screenshot or None,
            screenshot_after=top_screenshot or None,
            replay={'action': 'scroll', 'selector': 'document.scrollingElement', 'value': '0', 'source_url': page_url},
            parent_component='full_page_inventory',
        ))
        sequence += 1

    return interactions, sequence, discovered, {
        'scroll_count': scroll_count,
        'control_count': len(discovered),
        'document_height': int(final_metrics.get('height', 0) or 0),
    }

def _resolve_observation_locator(page, candidate: ClickCandidate):
    """Resolve the captured element against the current visible DOM, not a stale global index."""
    selectors = [candidate.selector] if candidate.selector else []
    if candidate.element_id:
        selectors.append(f'#{candidate.element_id}')
    if candidate.href and candidate.tag == 'a':
        selectors.append(f'a[href="{candidate.href}"]')
    for selector in selectors:
        try:
            matches = page.locator(selector)
            for index in range(matches.count()):
                locator = matches.nth(index)
                if locator.is_visible() and locator.is_enabled():
                    return locator
        except Exception:
            continue
    label = _safe_text(candidate.text or candidate.value)
    if label:
        try:
            role = candidate.role or ('link' if candidate.tag == 'a' else 'button' if candidate.tag == 'button' else None)
            matches = page.get_by_role(role, name=label, exact=True) if role else page.get_by_text(label, exact=True)
            for index in range(matches.count()):
                locator = matches.nth(index)
                if locator.is_visible() and locator.is_enabled():
                    return locator
        except Exception:
            pass
    raise RuntimeError(f'Visible target could not be resolved: {label or candidate.selector or candidate.href}')

def _execute_observation_click(page, candidate: ClickCandidate, sequence: int, current_url: str, stream_key: str = '', objective: str = '', live_preview: bool = False) -> Interaction | None:
    if candidate.input_type in {'password', 'file'} or not _is_safe_observation_click(candidate.text or candidate.value, candidate.tag, objective):
        _publish_agent_event(stream_key, {
            'type': 'interaction_skipped',
            'status': 'Skipped',
            'url': page.url or current_url,
            'element': candidate.text or candidate.value or candidate.href,
            'tag': candidate.tag,
            'selector': candidate.selector,
            'reason': 'Unsafe, password, or file control was not clicked by the read-only discovery agent.',
        })
        return None
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    stem = unique_filename(f'event_{sequence}', '')
    before = GENERATED_DIR / f'{stem}_before.png'
    after = GENERATED_DIR / f'{stem}_after.png'
    responses: list[dict[str, object]] = []
    popups: list[dict[str, object]] = []

    def on_response(response):
        if len(responses) < 50:
            responses.append({'url': response.url, 'method': response.request.method, 'status': response.status, 'resource_type': response.request.resource_type, 'sequence_id': sequence})

    def on_popup(popup):
        popups.append({'url': popup.url, 'title': popup.title() if not popup.is_closed() else '', 'type': 'new_tab_or_popup', 'sequence_id': sequence})

    page.on('response', on_response)
    page.on('popup', on_popup)
    try:
        locator = _resolve_observation_locator(page, candidate)
        box = locator.bounding_box()
        before_url = page.url
        before_title = page.title()
        dom_before = _capture_dom_snapshot(page, 30000)
        iframe_before = [{'url': frame.url, 'name': frame.name} for frame in page.frames]
        coordinates = {'x': float(box['x']), 'y': float(box['y']), 'width': float(box['width']), 'height': float(box['height'])} if box else {}
        page.screenshot(path=str(before), full_page=False)
        _publish_agent_event(stream_key, {
            'type': 'click_started',
            'status': 'Clicking',
            'url': before_url,
            'title': before_title,
            'element': candidate.text or candidate.value or candidate.href,
            'tag': candidate.tag,
            'role': candidate.role,
            'selector': candidate.selector or candidate.href or candidate.text,
            'href': candidate.href,
            'coordinates': coordinates,
            'screenshot_before': str(before),
            'sequence': sequence,
        })
        if live_preview:
            show_live_pointer(page, coordinates, candidate.text or candidate.value or candidate.href or 'Click', pulse=True)
        locator.click(timeout=5000, no_wait_after=True)
        if live_preview:
            page.wait_for_timeout(450)
        _publish_agent_event(stream_key, {
            'type': 'navigation_wait',
            'status': 'Waiting',
            'url': before_url,
            'element': candidate.text or candidate.value or candidate.href,
            'expected_destination': candidate.href or '',
            'sequence': sequence,
        })
        ready_condition = _wait_for_page_ready(page, timeout_ms=15000, settle_ms=900)
        after_url = page.url
        after_title = page.title()
        dom_after = _capture_dom_snapshot(page, 30000)
        iframe_after = [{'url': frame.url, 'name': frame.name} for frame in page.frames]
        page.screenshot(path=str(after), full_page=False)
        state_after = 'navigated' if after_url != before_url else ('updated' if dom_after != dom_before else 'no_change')
        result = 'new_page' if after_url != before_url else ('same_page_update' if state_after == 'updated' else 'no_change')
        _publish_agent_event(stream_key, {
            'type': 'click_completed',
            'status': 'Navigated' if after_url != before_url else 'Updated' if state_after == 'updated' else 'No change',
            'url': before_url,
            'title': before_title,
            'element': candidate.text or candidate.value or candidate.href,
            'tag': candidate.tag,
            'role': candidate.role,
            'selector': candidate.selector or candidate.href or candidate.text,
            'destination_url': after_url,
            'destination_title': after_title,
            'result': result,
            'coordinates': coordinates,
            'network_count': len(responses),
            'popup_count': len(popups),
            'iframe_count': len(iframe_after or iframe_before),
            'screenshot_after': str(after),
            'sequence': sequence,
        })
        return _build_interaction(sequence_id=sequence, interaction_number=sequence, page_url=before_url, element_type=candidate.tag or 'control', element_label=candidate.text or candidate.value or candidate.href, role=candidate.role, element_id=candidate.element_id or None, selector=candidate.selector or candidate.href or candidate.text, action='click', value=candidate.value or None, state_before='visible_enabled', state_after=state_after, resulted_in=result, wait_condition=ready_condition, destination_url=after_url, coordinates=coordinates, network_events=responses, event_timestamp=timestamp, screenshot_before=str(before), screenshot_after=str(after), iframe_inventory=iframe_after or iframe_before, popup_activity=popups, replay={'action': 'click', 'selector': candidate.selector or candidate.href or candidate.text, 'value': candidate.value or None, 'source_url': before_url, 'destination_url': after_url}, is_dynamic_element=True, is_custom_component=candidate.tag == 'button', parent_component='browser_agent_observed_click', dom_snapshot_before=dom_before, dom_snapshot_after=dom_after)
    except Exception as exc:
        error_text = f'{type(exc).__name__}: {exc}'
        _publish_agent_event(stream_key, {
            'type': 'click_failed',
            'status': 'Failed',
            'url': page.url or current_url,
            'element': candidate.text or candidate.value or candidate.href,
            'tag': candidate.tag,
            'selector': candidate.selector or candidate.href or candidate.text,
            'result': error_text,
            'network_count': len(responses),
            'sequence': sequence,
        })
        error_snapshot = _capture_dom_snapshot(page)
        error_screenshot = _capture_viewport_screenshot(page, f'event_{sequence}_error')
        return _build_interaction(sequence_id=sequence, interaction_number=sequence, page_url=page.url or current_url, element_type=candidate.tag or 'control', element_label=candidate.text or candidate.value or candidate.href, role=candidate.role, element_id=candidate.element_id or None, selector=candidate.selector or candidate.href or candidate.text, action='click', value=candidate.value or None, state_before='visible', state_after='error', resulted_in=f'click_failed: {error_text}', wait_condition='timeout', network_events=responses, event_timestamp=timestamp, popup_activity=popups, replay={'action': 'click', 'selector': candidate.selector or candidate.href or candidate.text, 'source_url': current_url}, parent_component='browser_agent_observed_click', screenshot_after=error_screenshot or None, dom_snapshot_after=error_snapshot or None)
    finally:
        page.remove_listener('response', on_response)
        page.remove_listener('popup', on_popup)


def _execute_observation_hover(page, candidate: ClickCandidate, sequence: int, current_url: str, stream_key: str = '', live_preview: bool = False) -> tuple[Interaction | None, list[ClickCandidate]]:
    """Hover a visible menu/control, then rescan for newly revealed objective targets."""
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    stem = unique_filename(f'event_{sequence}_hover', '')
    before = GENERATED_DIR / f'{stem}_before.png'
    after = GENERATED_DIR / f'{stem}_after.png'
    try:
        locator = _resolve_observation_locator(page, candidate)
        box = locator.bounding_box()
        before_url = page.url or current_url
        before_title = page.title()
        dom_before = _capture_dom_snapshot(page)
        coordinates = {'x': float(box['x']), 'y': float(box['y']), 'width': float(box['width']), 'height': float(box['height'])} if box else {}
        page.screenshot(path=str(before), full_page=False)
        _publish_agent_event(stream_key, {
            'type': 'hover_started',
            'status': 'Hovering',
            'url': before_url,
            'title': before_title,
            'element': candidate.text or candidate.value or candidate.href,
            'tag': candidate.tag,
            'role': candidate.role,
            'selector': candidate.selector or candidate.href or candidate.text,
            'coordinates': coordinates,
            'screenshot_before': str(before),
            'sequence': sequence,
        })
        if live_preview:
            show_live_pointer(page, coordinates, candidate.text or candidate.value or candidate.href or 'Hover')
        locator.hover(timeout=5000)
        if live_preview:
            page.wait_for_timeout(450)
        ready_condition = _wait_for_page_ready(page, timeout_ms=8000, settle_ms=900)
        dom_after = _capture_dom_snapshot(page)
        page.screenshot(path=str(after), full_page=False)
        revealed_actions = _extract_clickable_actions(page)
        result = 'menu_revealed' if dom_after != dom_before else 'hover_no_change'
        _publish_agent_event(stream_key, {
            'type': 'hover_completed',
            'status': 'Menu revealed' if result == 'menu_revealed' else 'Hover completed',
            'url': page.url or before_url,
            'title': page.title(),
            'element': candidate.text or candidate.value or candidate.href,
            'selector': candidate.selector or candidate.href or candidate.text,
            'result': result,
            'candidate_count_after_hover': len(revealed_actions),
            'coordinates': coordinates,
            'screenshot_after': str(after),
            'sequence': sequence,
        })
        interaction = _build_interaction(
            sequence_id=sequence,
            interaction_number=sequence,
            page_url=before_url,
            element_type=candidate.tag or 'menu',
            element_label=candidate.text or candidate.value or candidate.href,
            role=candidate.role,
            element_id=candidate.element_id or None,
            selector=candidate.selector or candidate.href or candidate.text,
            action='hover',
            value=candidate.value or None,
            state_before='visible_enabled',
            state_after='revealed' if result == 'menu_revealed' else 'visible',
            resulted_in=result,
            wait_condition=ready_condition,
            coordinates=coordinates,
            event_timestamp=timestamp,
            screenshot_before=str(before),
            screenshot_after=str(after),
            dom_snapshot_before=dom_before or None,
            dom_snapshot_after=dom_after or None,
            iframe_inventory=[{'url': frame.url, 'name': frame.name} for frame in page.frames],
            replay={'action': 'hover', 'selector': candidate.selector or candidate.href or candidate.text, 'source_url': before_url},
            is_dynamic_element=True,
            is_custom_component=True,
            parent_component='browser_agent_observed_hover',
        )
        return interaction, revealed_actions
    except Exception as exc:
        error_text = f'{type(exc).__name__}: {exc}'
        _publish_agent_event(stream_key, {
            'type': 'hover_failed',
            'status': 'Hover failed',
            'url': page.url or current_url,
            'element': candidate.text or candidate.value or candidate.href,
            'selector': candidate.selector or candidate.href or candidate.text,
            'result': error_text,
            'sequence': sequence,
        })
        interaction = _build_interaction(
            sequence_id=sequence,
            interaction_number=sequence,
            page_url=page.url or current_url,
            element_type=candidate.tag or 'menu',
            element_label=candidate.text or candidate.value or candidate.href,
            role=candidate.role,
            element_id=candidate.element_id or None,
            selector=candidate.selector or candidate.href or candidate.text,
            action='hover',
            value=candidate.value or None,
            state_before='visible',
            state_after='error',
            resulted_in=f'hover_failed: {error_text}',
            wait_condition='timeout',
            event_timestamp=timestamp,
            screenshot_after=_capture_viewport_screenshot(page, f'event_{sequence}_hover_error') or None,
            dom_snapshot_after=_capture_dom_snapshot(page) or None,
            replay={'action': 'hover', 'selector': candidate.selector or candidate.href or candidate.text, 'source_url': current_url},
            parent_component='browser_agent_observed_hover',
        )
        return interaction, _extract_clickable_actions(page)

def _candidate_ledger_key(page_url: str, candidate: ClickCandidate) -> str:
    return hashlib.sha1(f"{page_url}|{candidate.selector}|{candidate.href}|{candidate.text}".encode("utf-8")).hexdigest()[:16]


def _track_candidates(ledger: dict[str, dict[str, object]], page_url: str, application_url: str, candidates: list[ClickCandidate], objective: str = '') -> None:
    for candidate in candidates:
        key = _candidate_ledger_key(page_url, candidate)
        if key in ledger:
            continue
        target_url = _resolve_href(page_url or application_url, candidate.href) if candidate.href else ""
        external = bool(target_url and not _same_origin(application_url, target_url))
        safe = _is_safe_observation_click(candidate.text or candidate.value, candidate.tag, objective)
        status = "external" if external else "skipped_safety" if not safe else "discovered"
        reason = "Outside application origin" if external else "Unsafe or irreversible control" if not safe else "Awaiting exploration"
        ledger[key] = {
            "candidate_id": key, "page_url": page_url, "element": candidate.text or candidate.value or candidate.href,
            "selector": candidate.selector, "href": candidate.href, "tag": candidate.tag, "role": candidate.role,
            "status": status, "reason": reason,
        }


def _set_candidate_status(ledger: dict[str, dict[str, object]], page_url: str, candidate: ClickCandidate, status: str, reason: str) -> None:
    key = _candidate_ledger_key(page_url, candidate)
    if key in ledger:
        ledger[key]["status"] = status
        ledger[key]["reason"] = reason

def _crawl_with_playwright(application_url: str, parameters: dict[str, str], max_depth: int = 5, max_pages: int = 8, follow_links: bool = True, objective: str = "Discover the primary user journey from the application home page.", min_events: int = 10) -> tuple[list[JourneyStep], list[str], dict[str, object]]:
    max_depth = _normalise_crawl_setting(max_depth, 3, 0, 10)
    max_pages = _normalise_crawl_setting(max_pages, 8, 1, 50)
    min_events = _normalise_crawl_setting(min_events, 10, 1, 100)
    if sync_playwright is None:
        raise RuntimeError('Playwright is not installed')

    clear_events(application_url)
    profile_text = get_browser_agent_profile(application_url, objective)
    steps: list[JourneyStep] = []
    reasoning_bits: list[str] = []
    test_hints: list[str] = []
    visited: set[str] = set()
    queue: deque[tuple[str, int, int]] = deque([(application_url, 0, 0)])
    sequence = 1
    candidate_ledger: dict[str, dict[str, object]] = {}

    with sync_playwright() as playwright:
        cdp_url = os.environ.get('BROWSER_CDP_URL', '').strip()
        using_live_browser = False
        if cdp_url:
            try:
                browser = connect_live_browser(playwright, application_url, timeout_seconds=45)
                using_live_browser = True
                publish_event(application_url, {'type': 'status', 'status': 'Connected to live browser', 'url': application_url})
            except Exception as exc:
                publish_event(application_url, {'type': 'status', 'status': 'Live browser unavailable; using headless browser', 'url': application_url, 'result': f'{type(exc).__name__}: {exc}'})
                cdp_url = ''
                browser = playwright.chromium.launch(headless=True)
        else:
            browser = playwright.chromium.launch(headless=True)
        context = browser.contexts[0] if using_live_browser and browser.contexts else browser.new_context(viewport={'width': 1280, 'height': 800})
        if using_live_browser and context.pages:
            # noVNC renders the first tab; keep the API and live view aligned.
            page = context.pages[0]
        else:
            page = context.pages[0] if context.pages else context.new_page()
        try:
            page.bring_to_front()
        except Exception:
            pass
        live_observers = _install_live_page_observers(page, application_url)
        try:
            while queue and len(visited) < max_pages:
                current_url, depth, target_index = queue.popleft()
                target_index = max(0, min(int(target_index or 0), len(_objective_targets(objective))))
                if current_url in visited:
                    continue
                visited.add(current_url)
                publish_event(application_url, {'type': 'status', 'status': 'Navigating', 'url': current_url, 'depth': depth})
                page.goto(current_url, wait_until='domcontentloaded', timeout=30000)
                if using_live_browser:
                    prepare_live_page(page)
                    page.wait_for_timeout(350)
                ready_condition = _wait_for_page_ready(page)
                page_snapshot = _capture_dom_snapshot(page)
                page_screenshot = _capture_viewport_screenshot(page, f'page_{sequence}_loaded')
                signals = _extract_page_signals(page)
                current_title = _derive_page_name(page.url, signals.get('title') or page.title())
                publish_event(application_url, {'type': 'page_loaded', 'status': 'Waiting', 'url': page.url, 'title': current_title, 'depth': depth, 'dom_snapshot_captured': bool(page_snapshot), 'screenshot_after': page_screenshot})
                headings = [h for h in signals.get('headings', []) if h]
                buttons = [b for b in signals.get('buttons', []) if b]
                links = [l for l in signals.get('links', []) if l]
                inputs = [i for i in signals.get('inputs', []) if i]
                menus = [m for m in signals.get('menus', []) if m]
                sections = [s for s in signals.get('sections', []) if s]
                forms = signals.get('forms', []) or []
                publish_event(application_url, {
                    'type': 'page_scanned',
                    'status': 'Inspecting DOM',
                    'url': page.url,
                    'title': current_title,
                    'depth': depth,
                    'counts': {
                        'headings': len(headings),
                        'buttons': len(buttons),
                        'links': len(links),
                        'inputs': len(inputs),
                        'menus': len(menus),
                        'forms': len(forms),
                    },
                    'visible_elements': _signal_preview_items(signals),
                    'result': f'Found {len(buttons)} buttons, {len(links)} links, {len(inputs)} inputs, and {len(forms)} forms.',
                })

                interactions: list[Interaction] = []
                interactions.append(_build_interaction(
                    sequence_id=sequence,
                    interaction_number=1,
                    page_url=page.url,
                    element_type='page',
                    element_label=current_title,
                    selector=page.url,
                    action='open',
                    value=None,
                    state_before='unknown',
                    state_after='loaded',
                    resulted_in='page_load',
                    wait_condition=ready_condition,
                    is_dynamic_element=False,
                    is_custom_component=False,
                    is_shadow_dom=False,
                    parent_component='browser_root',
                    screenshot_after=page_screenshot or None,
                    dom_snapshot_after=page_snapshot or None,
                    replay={'action': 'open', 'selector': page.url, 'source_url': page.url},
                ))
                sequence += 1

                scan_summary = f'Page scan found {len(headings)} headings, {len(buttons)} buttons, {len(links)} links, {len(inputs)} inputs, {len(menus)} menus, and {len(forms)} forms'
                interactions.append(_build_interaction(
                    sequence_id=sequence,
                    interaction_number=2,
                    page_url=page.url,
                    element_type='scan',
                    element_label='page scan',
                    selector='document.querySelectorAll',
                    action='inspect',
                    value=None,
                    state_before='n/a',
                    state_after='scanned',
                    resulted_in=scan_summary,
                    wait_condition='none',
                    parent_component='page_inventory',
                    screenshot_after=page_screenshot or None,
                    dom_snapshot_after=page_snapshot or None,
                    replay={'action': 'inspect', 'selector': 'document.querySelectorAll', 'source_url': page.url},
                ))
                sequence += 1
                reasoning_bits.append(scan_summary)

                explicit_action_targets = _objective_action_targets(objective)
                full_page_inventory_enabled = _requires_full_page_inventory(objective)
                generic_inventory_mode = full_page_inventory_enabled and not explicit_action_targets
                if full_page_inventory_enabled:
                    full_inventory_interactions, sequence, actions_for_inventory, inventory_summary = _capture_full_page_inventory(
                        page,
                        sequence,
                        page.url,
                        application_url,
                        return_to_top=bool(explicit_action_targets),
                        live_preview=using_live_browser,
                    )
                    interactions.extend(full_inventory_interactions)
                    signals = _extract_page_signals(page)
                    reasoning_bits.append(
                        f"Full page inventory captured {inventory_summary['control_count']} controls across "
                        f"{inventory_summary['scroll_count']} scrolls and {inventory_summary['document_height']} pixels"
                    )
                else:
                    actions_for_inventory = _extract_clickable_actions(page)
                    minimum_remaining = max(0, min_events - sequence + 1)
                    if minimum_remaining > 0:
                        inventory_interactions, sequence = _build_inventory_interactions(
                            actions_for_inventory,
                            sequence,
                            page.url,
                            min(minimum_remaining, 4),
                            application_url,
                            page_snapshot,
                            page_screenshot,
                        )
                        interactions.extend(inventory_interactions)
                _track_candidates(candidate_ledger, page.url, application_url, actions_for_inventory, objective)

                if generic_inventory_mode and follow_links and depth < max_depth and not _objective_limits_to_current_page(objective):
                    available_slots = max(0, max_pages - len(visited) - len(queue))
                    for candidate in _generic_internal_link_candidates(
                        actions_for_inventory,
                        application_url,
                        page.url,
                        objective,
                        limit=available_slots,
                    ):
                        target_url = _resolve_href(page.url, candidate.href).split('#', 1)[0]
                        if target_url in visited or any(queued_url == target_url for queued_url, _, _ in queue):
                            continue
                        queue.append((target_url, depth + 1, 0))
                        _set_candidate_status(candidate_ledger, page.url, candidate, 'queued', 'Queued for generic internal-page discovery')
                        publish_event(application_url, {
                            'type': 'page_queued',
                            'status': 'Queued for exploration',
                            'url': page.url,
                            'destination_url': target_url,
                            'element': candidate.text or candidate.href,
                            'selector': candidate.selector,
                        })

                objective_targets = [] if generic_inventory_mode else _objective_targets(objective)

                hovered_targets: set[str] = set()
                should_follow_objective = bool(objective_targets) and depth < max_depth
                should_browse_links = follow_links and depth < max_depth and not generic_inventory_mode
                if should_follow_objective or should_browse_links:
                    current_target_index = target_index
                    performed_clicks = 0
                    max_objective_clicks = max(1, min(max(len(objective_targets), min_events), max_pages * 3, 20))
                    while performed_clicks < max_objective_clicks:
                        actions = _extract_clickable_actions(page)
                        _track_candidates(candidate_ledger, page.url, application_url, actions, objective)
                        all_scored = sorted(((_score_candidate(action, profile_text, objective), action) for action in actions), key=lambda item: item[0], reverse=True)
                        selected_actions = _choose_objective_actions(actions, profile_text, objective, current_target_index)
                        current_objective_target = objective_targets[current_target_index] if current_target_index < len(objective_targets) else ''
                        publish_event(application_url, {
                            'type': 'candidate_actions',
                            'status': 'Planning next action',
                            'url': page.url,
                            'title': current_title,
                            'depth': depth,
                            'candidate_count': len(actions),
                            'objective_targets': objective_targets,
                            'current_target': current_objective_target,
                            'top_candidates': [_candidate_preview(action, score) for score, action in all_scored[:10]],
                        })
                        if not selected_actions:
                            if _is_consent_objective_target(current_objective_target):
                                publish_event(application_url, {
                                    'type': 'consent_not_present',
                                    'status': 'Cookie consent previously resolved',
                                    'url': page.url,
                                    'title': current_title,
                                    'current_target': current_objective_target,
                                    'reason': 'The optional consent control was not visible, so business-page exploration continued.',
                                })
                                current_target_index += 1
                                continue
                            publish_event(application_url, {
                                'type': 'objective_waiting',
                                'status': 'No matching target found',
                                'url': page.url,
                                'title': current_title,
                                'current_target': current_objective_target,
                                'reason': 'The current page did not expose a visible control matching the next objective target.',
                            })
                            break

                        next_objective_target = objective_targets[current_target_index + 1] if current_target_index + 1 < len(objective_targets) else ''
                        hover_candidate = selected_actions[0]
                        hover_required = _objective_requires_hover(objective, current_objective_target, hover_candidate)
                        click_explicit = _objective_explicitly_clicks_target(objective, current_objective_target, hover_candidate)
                        should_hover_target = (
                            current_objective_target not in hovered_targets
                            and _should_hover_target(hover_candidate, objective, current_objective_target, next_objective_target, actions)
                        )
                        if should_hover_target:
                            hover_interaction, revealed_actions = _execute_observation_hover(page, hover_candidate, sequence, page.url, application_url, live_preview=using_live_browser)
                            hover_failed = hover_interaction is None or any(
                                word in str(hover_interaction.resulted_in or '').lower()
                                for word in ('failed', 'error', 'timeout', 'blocked')
                            )
                            if hover_interaction is not None:
                                _set_candidate_status(
                                    candidate_ledger,
                                    page.url,
                                    hover_candidate,
                                    'failed' if hover_failed else 'succeeded',
                                    hover_interaction.resulted_in or 'Hover observed',
                                )
                                interactions.append(hover_interaction)
                                sequence += 1
                                performed_clicks += 1
                            hovered_targets.add(current_objective_target)
                            if hover_failed:
                                publish_event(application_url, {
                                    'type': 'objective_waiting',
                                    'status': 'Required hover failed',
                                    'url': page.url,
                                    'title': current_title,
                                    'current_target': current_objective_target,
                                    'reason': 'The required hover action failed; the target was not clicked as a fallback.',
                                })
                                break
                            if next_objective_target:
                                if _target_visible_in_actions(revealed_actions, next_objective_target):
                                    publish_event(application_url, {
                                        'type': 'objective_target_revealed',
                                        'status': 'Target revealed',
                                        'url': page.url,
                                        'title': current_title,
                                        'hovered_element': hover_candidate.text or hover_candidate.value or hover_candidate.href,
                                        'revealed_target': next_objective_target,
                                        'candidate_count': len(revealed_actions),
                                    })
                                    current_target_index = min(current_target_index + 1, len(objective_targets))
                                    continue
                                publish_event(application_url, {
                                    'type': 'objective_waiting',
                                    'status': 'Menu target not visible after hover',
                                    'url': page.url,
                                    'title': current_title,
                                    'current_target': current_objective_target,
                                    'required_child_target': next_objective_target,
                                    'hovered_element': hover_candidate.text or hover_candidate.value or hover_candidate.href,
                                    'reason': 'The required child target was not visible after the menu hover; the parent link was not clicked.',
                                })
                                break
                            if hover_required and not click_explicit:
                                publish_event(application_url, {
                                    'type': 'hover_only_completed',
                                    'status': 'Hover completed',
                                    'url': page.url,
                                    'title': current_title,
                                    'current_target': current_objective_target,
                                    'reason': 'The objective requested hover only; click execution was intentionally suppressed.',
                                })
                                current_target_index = min(current_target_index + 1, len(objective_targets))
                                continue
                        if hover_required and not click_explicit:
                            publish_event(application_url, {
                                'type': 'candidate_skipped',
                                'status': 'Click suppressed',
                                'url': page.url,
                                'title': current_title,
                                'current_target': current_objective_target,
                                'reason': 'This is a hover-only objective target and cannot enter the click executor.',
                            })
                            break
                        scored = sorted(((_score_candidate(action, profile_text, objective), action) for action in selected_actions), key=lambda item: item[0], reverse=True)
                        clicked_this_round = False
                        for score, action in scored:
                            if performed_clicks > 0 and current_objective_target:
                                target_match_score, _ = _objective_match_score(action, current_objective_target)
                                if target_match_score <= 0:
                                    publish_event(application_url, {
                                        'type': 'candidate_skipped',
                                        'status': 'Skipped',
                                        'url': page.url,
                                        'title': current_title,
                                        'element': action.text or action.value or action.href,
                                        'selector': action.selector,
                                        'score': score,
                                        'reason': 'After the first click, the agent only follows controls that match the next explicit objective target.',
                                    })
                                    continue
                            if score < 15 and not _looks_like_safe_cta(action.text or action.value, action.tag):
                                _set_candidate_status(candidate_ledger, page.url, action, 'skipped_objective', 'Candidate did not match the objective strongly enough')
                                publish_event(application_url, {
                                    'type': 'candidate_skipped',
                                    'status': 'Skipped',
                                    'url': page.url,
                                    'title': current_title,
                                    'element': action.text or action.value or action.href,
                                    'selector': action.selector,
                                    'score': score,
                                    'reason': 'Candidate did not match the journey objective strongly enough.',
                                })
                                continue
                            target_url = _resolve_href(application_url, action.href) if action.href else page.url
                            if action.href and not _same_origin(application_url, target_url):
                                publish_event(application_url, {
                                    'type': 'candidate_skipped',
                                    'status': 'Skipped',
                                    'url': page.url,
                                    'title': current_title,
                                    'element': action.text or action.value or action.href,
                                    'selector': action.selector,
                                    'score': score,
                                    'reason': 'External link skipped to keep the crawl inside the application boundary.',
                                })
                                continue
                            publish_event(application_url, {
                                'type': 'target_selected',
                                'status': 'Target selected',
                                'url': page.url,
                                'title': current_title,
                                'element': action.text or action.value or action.href,
                                'tag': action.tag,
                                'role': action.role,
                                'selector': action.selector,
                                'href': action.href,
                                'score': score,
                                'current_target': current_objective_target,
                                'expected_destination': target_url,
                            })
                            publish_event(application_url, {'type': 'clicking', 'status': 'Clicking', 'url': page.url, 'title': current_title, 'element': action.text or action.value or action.href, 'tag': action.tag, 'selector': action.selector, 'score': score, 'current_target': current_objective_target})
                            _set_candidate_status(candidate_ledger, page.url, action, 'attempted', 'Agent selected this control')
                            before_click_url = page.url
                            observed = _execute_observation_click(page, action, sequence, page.url, application_url, objective, live_preview=using_live_browser)
                            if observed is not None:
                                click_failed = any(word in str(observed.resulted_in or '').lower() for word in ('failed', 'error', 'timeout', 'blocked'))
                                _set_candidate_status(candidate_ledger, before_click_url, action, 'failed' if click_failed else 'succeeded', observed.resulted_in or 'Click observed')
                                # A click may open a new tab or popup. Promote that
                                # page before continuing so Playwright, noVNC, and
                                # the persisted journey all follow the same view.
                                if observed.popup_activity and len(page.context.pages) > 1:
                                    popup_page = page.context.pages[-1]
                                    try:
                                        popup_page.wait_for_load_state('domcontentloaded', timeout=15000)
                                    except Exception:
                                        pass
                                    try:
                                        popup_page.bring_to_front()
                                    except Exception:
                                        pass
                                    popup_url = popup_page.url
                                    if popup_url and popup_url != 'about:blank':
                                        # noVNC renders the first Chromium tab. Keep
                                        # that visible tab on the same destination
                                        # as the promoted popup so the stream shows
                                        # the navigation that the agent performed.
                                        visible_page = page.context.pages[0]
                                        if visible_page is not popup_page:
                                            try:
                                                visible_page.goto(popup_url, wait_until='domcontentloaded', timeout=30000)
                                                _wait_for_page_ready(visible_page)
                                                visible_page.bring_to_front()
                                                page = visible_page
                                            except Exception:
                                                page = popup_page
                                        else:
                                            page = popup_page
                                        observed = observed.model_copy(update={
                                            'destination_url': popup_url,
                                            'dom_snapshot_after': _capture_dom_snapshot(popup_page),
                                            'screenshot_after': _capture_viewport_screenshot(popup_page, f'event_{sequence}_popup_after'),
                                            'resulted_in': 'new_page',
                                        })
                                interactions.append(observed)
                                sequence += 1
                                performed_clicks += 1
                                clicked_this_round = True
                                current_url = page.url
                                current_title = _derive_page_name(page.url, page.title())
                                try:
                                    next_signals = _extract_page_signals(page)
                                    signals = next_signals
                                    publish_event(application_url, {
                                        'type': 'page_scanned',
                                        'status': 'Inspecting DOM',
                                        'url': page.url,
                                        'title': current_title,
                                        'depth': depth + performed_clicks,
                                        'counts': {
                                            'headings': len([h for h in next_signals.get('headings', []) if h]),
                                            'buttons': len([b for b in next_signals.get('buttons', []) if b]),
                                            'links': len([l for l in next_signals.get('links', []) if l]),
                                            'inputs': len([i for i in next_signals.get('inputs', []) if i]),
                                            'menus': len([m for m in next_signals.get('menus', []) if m]),
                                            'forms': len(next_signals.get('forms', []) or []),
                                        },
                                        'visible_elements': _signal_preview_items(next_signals),
                                        'result': 'Page state refreshed after click.',
                                    })
                                except Exception as exc:
                                    next_signals = signals
                                    publish_event(application_url, {'type': 'page_scan_failed', 'status': 'Scan failed', 'url': page.url, 'title': current_title, 'result': f'{type(exc).__name__}: {exc}'})
                                if observed.destination_url and observed.destination_url != before_click_url:
                                    transition_interactions = [_build_interaction(sequence_id=sequence, interaction_number=1, page_url=observed.destination_url, element_type='page', element_label=current_title, selector=observed.destination_url, action='open', value=None, state_before='navigation', state_after='loaded', resulted_in=f'navigated_from: {before_click_url}', wait_condition='domcontentloaded', parent_component='browser_navigation', screenshot_after=observed.screenshot_after, dom_snapshot_after=observed.dom_snapshot_after, replay={'action': 'open', 'selector': observed.destination_url, 'source_url': before_click_url})]
                                    sequence += 1
                                    steps.append(_page_to_step(len(steps) + 1, depth + performed_clicks, observed.destination_url, current_title, next_signals, transition_interactions))
                                    # Queue the destination so the next page is scanned and its clicks are captured.
                                    if observed.destination_url not in visited and len(visited) + len(queue) < max_pages:
                                        queue.append((observed.destination_url, depth + 1, min(current_target_index + 1, len(objective_targets))))
                                current_target_index = min(current_target_index + 1, len(objective_targets))
                            break
                        if not clicked_this_round:
                            break
                        if objective_targets and current_target_index >= len(objective_targets):
                            publish_event(application_url, {
                                'type': 'objective_completed',
                                'status': 'Objective path completed',
                                'url': page.url,
                                'title': current_title,
                                'click_count': performed_clicks,
                            })
                            break
                final_remaining = max(0, min_events - sequence + 1)
                if final_remaining > 0:
                    final_inventory, sequence = _build_inventory_interactions(_extract_clickable_actions(page), sequence, page.url, final_remaining, application_url, _capture_dom_snapshot(page), _capture_viewport_screenshot(page, f'page_{sequence}_final_inventory'))
                    interactions.extend(final_inventory)
                steps.append(_page_to_step(len(steps) + 1, depth, page.url, current_title, signals, interactions))
        finally:
            _remove_live_page_observers(page, live_observers)
            if not using_live_browser:
                browser.close()

    publish_event(application_url, {'type': 'status', 'status': 'Completed', 'url': steps[-1].page_url if steps else application_url, 'step_count': len(steps), 'event_count': sum(len(step.interactions) for step in steps)})

    return steps, reasoning_bits, {'candidate_ledger': list(candidate_ledger.values()), 'crawl_limits': {'max_depth': max_depth, 'max_pages': max_pages, 'min_events': min_events, 'follow_links': follow_links}}


def _build_browser_use_result(result_text: str, application_url: str, runtime: dict[str, object], steps: list[JourneyStep], crawl_reasoning: list[str], objective: str) -> ExplorationResult:
    title = _derive_page_name(application_url)
    reasoning = ' | '.join(([result_text[:4000]] if result_text else []) + crawl_reasoning)
    journey = JourneyRecord(
        journey_id=str(uuid4()),
        journey_title=f'{title} - Browser Use Discovery',
        starting_point=title,
        starting_url=application_url,
        outcome='Exploration Complete',
        outcome_detail='Browser-use selected the exploration path; Playwright captured the observed pages and controls.',
        reasoning=reasoning,
        total_depth=max((step.depth_level for step in steps), default=0),
        test_hints={'browser_use_enabled': True, 'browser_model': runtime.get('browser_model', 'gpt-4o-mini'), 'supervisor_model': runtime.get('supervisor_model', runtime.get('browser_model', 'gpt-4o-mini')), 'supervisor_enabled': runtime.get('supervisor_enabled', True), 'cdp_url': runtime.get('cdp_url'), 'capture_source': 'browser_use+playwright', 'journey_objective': objective, 'observed_page_count': len(steps), 'observed_interaction_count': sum(len(step.interactions) for step in steps), 'preconditions': [], 'test_tags': ['browser_use', 'journey', 'discovery']},
        steps=steps,
    )
    return ExplorationResult(
        exploration_metadata=ExplorationMetadata(app_url=application_url, starting_feature=title, task_input=objective, depth_level=max((step.depth_level for step in steps), default=0), is_pre_login_scoped=False, total_journeys_discovered=1, exploration_timestamp=datetime.now(timezone.utc).isoformat(), viewport={'width': 1280, 'height': 800}, browser='browser_use+playwright'),
        journeys=[journey],
    )
def _persist_browser_run_artifacts(exploration: ExplorationResult, runtime: dict[str, object]) -> dict[str, str]:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_json_name = unique_filename(f'browser_run_{timestamp}', '.json')
    run_md_name = unique_filename(f'browser_run_{timestamp}', '.md')
    json_path = write_json_file(run_json_name, exploration.model_dump())
    report_lines = [
        '# Browser Agent Run Report',
        '',
        f"- Browser Use Enabled: {runtime.get('browser_use_enabled', False)}",
        f"- Browser Model: {runtime.get('browser_model', '')}",
        f"- Supervisor Model: {runtime.get('supervisor_model', '')}",
        f"- Journey Count: {len(exploration.journeys)}",
        f"- Starting URL: {exploration.exploration_metadata.app_url}",
        f"- Timestamp: {exploration.exploration_metadata.exploration_timestamp}",
    ]
    md_path = write_markdown_file(run_md_name, '\n'.join(report_lines))
    return {'json_path': str(json_path), 'report_path': str(md_path)}


def _crawl_html_fallback(application_url: str, parameters: dict[str, str]) -> tuple[list[JourneyStep], list[str], list[str]]:
    request = Request(application_url, headers={'User-Agent': 'Mozilla/5.0 Journey-AI/1.0'})
    with urlopen(request, timeout=20) as response:
        html = response.read().decode('utf-8', errors='ignore')
    parser = _SimplePageParser()
    parser.feed(html)
    title = _derive_page_name(application_url, parser.title)
    headings = [h for h in parser.headings if h][:4]
    buttons = [b for b in parser.buttons if b][:6]
    links = [l for l in parser.links if l][:6]
    inputs = [i for i in parser.inputs if i][:6]
    menus = [m for m in parser.menus if m][:3]
    sections = [s for s in parser.sections if s][:3]

    interactions: list[Interaction] = [
        _build_interaction(
            sequence_id=1,
            interaction_number=1,
            page_url=application_url,
            element_type='page',
            element_label=title,
            selector=application_url,
            action='open',
            value=None,
            state_before='unknown',
            state_after='loaded',
            resulted_in='page_load',
            wait_condition='domcontentloaded',
            parent_component='landing_page',
        )
    ]
    if headings or buttons or links or inputs or menus or sections:
        interactions.append(_build_interaction(
            sequence_id=2,
            interaction_number=2,
            page_url=application_url,
            element_type='scan',
            element_label='page scan',
            selector='document.querySelectorAll',
            action='inspect',
            value=None,
            state_before='n/a',
            state_after='scanned',
            resulted_in='page_scan',
            wait_condition='none',
            parent_component='page_inventory',
        ))
    for idx, heading in enumerate(headings, start=3):
        interactions.append(_build_interaction(sequence_id=idx, interaction_number=idx, page_url=application_url, element_type='heading', element_label=heading, selector='h1,h2,h3', action='inspect', value=None, state_before='visible', state_after='visible', resulted_in='content_discovered', wait_condition='none', parent_component='content_area'))
    step = _build_step(1, 0, title, application_url, interactions)
    reasoning = [f'Loaded {application_url}', f'Heading count: {len(headings)}', f'Button count: {len(buttons)}', f'Link count: {len(links)}']
    return [step], reasoning, []



def _normalise_crawl_setting(value: object, default: int, minimum: int, maximum: int) -> int:
    """Keep API/UI crawl limits usable when clients send null or invalid values."""
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _normalise_crawl_settings(crawl_settings: dict[str, object] | None) -> tuple[int, int, bool, int]:
    settings = crawl_settings or {}
    max_depth = _normalise_crawl_setting(settings.get('max_depth'), 3, 0, 10)
    max_pages = _normalise_crawl_setting(settings.get('max_pages'), 8, 1, 50)
    min_events = _normalise_crawl_setting(settings.get('min_events'), 10, 1, 100)
    follow_links = settings.get('follow_links', True)
    if isinstance(follow_links, str):
        follow_links = follow_links.strip().lower() in {'1', 'true', 'yes', 'on'}
    else:
        follow_links = bool(follow_links)
    return max_depth, max_pages, follow_links, min_events
def explore_application(application_url: str, parameters: dict[str, str], crawl_settings: dict[str, object] | None = None, objective: str = "Discover the primary user journey from the application home page.") -> ExplorationResult:
    max_depth, max_pages, follow_links, min_events = _normalise_crawl_settings(crawl_settings)
    runtime = _runtime_browser_config()
    runtime['min_events'] = min_events
    metadata = ExplorationMetadata(
        app_url=application_url,
        starting_feature=_derive_page_name(application_url),
        task_input=objective,
        depth_level=max_depth,
        is_pre_login_scoped=False,
        total_journeys_discovered=1,
        exploration_timestamp=datetime.now(timezone.utc).isoformat(),
        viewport={'width': 1280, 'height': 800},
        browser='browser_use' if runtime['browser_use_enabled'] and _browser_use_available() else 'chromium',
    )

    journey_id = str(uuid4())
    browser_use_result = None
    browser_use_error = ''
    mcp_result = None
    mcp_error = ''
    playwright_error = ''
    capture_business: dict[str, object] = {}
    if runtime.get('playwright_mcp_enabled') and explore_with_mcp is not None:
        try:
            mcp_result = explore_with_mcp(application_url, str(runtime.get('playwright_mcp_command', 'npx')), runtime.get('playwright_mcp_args') or ['-y', '@playwright/mcp@latest'])
        except Exception as exc:
            mcp_error = f'{type(exc).__name__}: {exc}'
    if runtime['browser_use_enabled'] and _browser_use_available():
        try:
            task = get_browser_agent_profile(application_url, objective)
            browser_use_result = _browser_use_to_journey(task, application_url, runtime, parameters, max_depth, max_pages, follow_links, objective)
        except Exception as exc:
            browser_use_error = f'{type(exc).__name__}: {exc}'
            browser_use_result = None

    try:
        # Browser-use supplies goal reasoning, while Playwright owns the connected
        # page and records the observable click, navigation, and DOM evidence.
        captured_steps, captured_reasoning, capture_business = _crawl_with_playwright(
            application_url,
            parameters,
            max_depth=max_depth,
            max_pages=max_pages,
            follow_links=follow_links,
            objective=objective,
            min_events=min_events,
        )
        if not isinstance(capture_business, dict):
            capture_business = {}
        steps = captured_steps
        reasoning_bits = captured_reasoning
        if browser_use_result is not None:
            reasoning_bits.insert(0, browser_use_result.journeys[0].reasoning)
            outcome = browser_use_result.journeys[0].outcome
            outcome_detail = browser_use_result.journeys[0].outcome_detail
        else:
            outcome = 'Exploration Complete'
            outcome_detail = 'Journey discovered successfully from the base URL.'
        if mcp_result:
            reasoning_bits.insert(0, 'Playwright MCP capture completed and snapshot captured.')
        fallback = False
    except Exception as exc:
        playwright_error = f'{type(exc).__name__}: {exc}'
        if browser_use_result is not None:
            steps = browser_use_result.journeys[0].steps
            reasoning_bits = [browser_use_result.journeys[0].reasoning, f'Playwright evidence capture failed: {playwright_error}']
            outcome = browser_use_result.journeys[0].outcome
            outcome_detail = browser_use_result.journeys[0].outcome_detail
            fallback = False
        else:
            try:
                steps, reasoning_bits, _ = _crawl_html_fallback(application_url, parameters)
                outcome = 'Exploration Blocked'
                outcome_detail = 'Browser automation was unavailable, so only the landing page was parsed. The journey objective was not executed.'
                reasoning_bits.insert(0, f'Playwright capture failed: {playwright_error}')
                fallback = True
            except Exception:
                steps = []
                reasoning_bits = []
                fallback = True
                step, reasoning_bits, _ = _build_url_specific_fallback(application_url, parameters)
                steps = step
                outcome = 'Exploration Blocked'
                outcome_detail = f'Browser exploration fell back to URL-level capture only. {playwright_error}'

    steps = _enrich_capture_identity(steps, journey_id)
    metadata.exploration_id = 'EXP-' + hashlib.sha1(f'{application_url}:{metadata.exploration_timestamp}'.encode('utf-8')).hexdigest()[:12]
    total_depth = max((step.depth_level for step in steps), default=0)
    title = _derive_page_name(application_url)
    if fallback:
        title = f'{title} - Discovered from base URL'
    reasoning = ' | '.join(reasoning_bits) if reasoning_bits else f'Captured {len(steps)} steps from the base URL.'
    journey = JourneyRecord(
        journey_id=journey_id,
        journey_title=title,
        starting_point=title,
        starting_url=application_url,
        outcome=outcome,
        outcome_detail=outcome_detail,
        reasoning=reasoning,
        session_boundary_reached=False,
        session_boundary_url=None,
        total_depth=total_depth,
        test_hints={
            'requires_auth': 'login' in application_url.lower() or 'disney' in application_url.lower(),
            'is_critical_path': True,
            'has_api_calls': False,
            'has_file_upload': False,
            'has_dynamic_elements': True,
            'has_validation_flows': True,
            'browser_use_enabled': runtime['browser_use_enabled'] and _browser_use_available(),
            'browser_use_error': browser_use_error,
            'playwright_mcp_enabled': bool(runtime.get('playwright_mcp_enabled')),
            'playwright_mcp_error': mcp_error,
            'playwright_error': playwright_error,
            'playwright_mcp_snapshot_captured': bool(mcp_result and mcp_result.get('snapshot')),
            'capture_source': ('browser_use+playwright' if browser_use_result else ('url_fallback' if outcome == 'Exploration Blocked' else ('html_fallback' if fallback else 'playwright'))),
            'journey_objective': objective,
            'objective_targets': _objective_targets(objective),
            'minimum_events_requested': min_events,
            'candidate_ledger': capture_business.get('candidate_ledger', []),
            'crawl_limits': capture_business.get('crawl_limits', {
                'max_depth': max_depth,
                'max_pages': max_pages,
                'min_events': min_events,
                'follow_links': follow_links,
            }),
            'browser_model': runtime['browser_model'],
            'supervisor_model': runtime['supervisor_model'],
            'browser_headers': runtime['browser_headers'],
            'preconditions': [],
            'test_tags': ['browser_agent', 'journey', 'discovery'],
            'data_dependencies': [],
            'exploration_id': metadata.exploration_id,
            'page_ids': [interaction.page_id for step in steps for interaction in step.interactions if interaction.page_id],
            'event_ids': [interaction.event_id for step in steps for interaction in step.interactions if interaction.event_id],
        },
        housekeeping_steps=[],
        steps=steps,
    )
    metadata.total_journeys_discovered = 1
    journey = journey.model_copy(update={'business_assurance': build_business_assurance(journey.model_dump(), metadata.model_dump())})
    exploration = ExplorationResult(exploration_metadata=metadata, journeys=[journey])
    _persist_browser_run_artifacts(exploration, runtime)
    return exploration

















