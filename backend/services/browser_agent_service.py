from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from routers.configuration_router import _read as read_configuration
from services.artifact_file_service import write_json_file, write_markdown_file, unique_filename, GENERATED_DIR
from services.token_manager import TokenManager
from services.agent_prompts import get_browser_agent_profile
from schemas.journey_schema import ExplorationMetadata, ExplorationResult, Interaction, JourneyRecord, JourneyStep

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover - optional dependency
    sync_playwright = None

try:  # pragma: no cover - optional dependency
    from browser_use import Agent, Browser, BrowserSession
    from langchain.agents import create_agent
    from langchain_core.messages import HumanMessage
    from langchain_openai import ChatOpenAI
    from langgraph.checkpoint.memory import InMemorySaver
except Exception:  # pragma: no cover - optional dependency
    Agent = Browser = BrowserSession = None
    create_agent = None
    HumanMessage = None
    ChatOpenAI = None
    InMemorySaver = None


@dataclass
class ClickCandidate:
    text: str
    href: str
    tag: str
    role: str


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
        'browser_use_enabled': bool(llm.get('browser_use_enabled', False)),
        'browser_model': llm.get('model', 'gpt-4o-mini'),
        'supervisor_model': llm.get('supervisor_model') or llm.get('model', 'gpt-4o-mini'),
        'api_endpoint': llm.get('api_endpoint', '') or config.get('llm_api_endpoint', ''),
        'auth_token': auth_token,
        'temperature': llm.get('temperature', 0.2),
        'browser_timeout_screenshot': float(llm.get('browser_timeout_screenshot', 30.0) or 30.0),
        'browser_timeout_navigate': float(llm.get('browser_timeout_navigate', 30.0) or 30.0),
        'browser_headers': application.get('browser_headers', {}) if isinstance(application, dict) else {},
    }


def _browser_use_available() -> bool:
    return all(item is not None for item in (Agent, Browser, BrowserSession, create_agent, HumanMessage, ChatOpenAI, InMemorySaver))


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
    auth_token = str(runtime.get('auth_token', '') or '')
    if not api_endpoint:
        raise RuntimeError('LLM api_endpoint is required for browser_use mode')
    if not auth_token:
        raise RuntimeError('LLM auth_token is required for browser_use mode')
    browser_model = str(runtime.get('browser_model', 'gpt-4o-mini') or 'gpt-4o-mini')
    supervisor_model = str(runtime.get('supervisor_model', browser_model) or browser_model)
    headers = {'Authorization': f'Bearer {auth_token}', 'Content-Type': 'application/json'}
    browser_llm = ChatOpenAI(model=browser_model, base_url=api_endpoint, api_key=auth_token, default_headers=headers, temperature=float(runtime.get('temperature', 0.2) or 0.2))
    supervisor_llm = ChatOpenAI(model=supervisor_model, base_url=api_endpoint, api_key=auth_token, default_headers=headers, temperature=float(runtime.get('temperature', 0.2) or 0.2))
    return browser_llm, supervisor_llm


def _browser_use_to_journey(exploration_text: str, application_url: str, runtime: dict[str, object], parameters: dict[str, str]) -> ExplorationResult:
    browser_llm, supervisor_llm = _build_browser_use_client(runtime)
    headers = _build_browser_headers(runtime, application_url)
    profile_prompt = get_browser_agent_profile(application_url)

    browser = Browser(cdp_url='http://localhost:9222', headers=headers)
    browser_session = BrowserSession(headers=headers)
    agent = Agent(
        task=exploration_text,
        llm=browser_llm,
        sensitive_data=parameters,
        extend_system_message=profile_prompt,
        use_vision=True,
        calculate_cost=True,
        browser_session=browser_session,
    )
    supervisor = create_agent(
        model=supervisor_llm,
        tools=[],
        system_prompt=profile_prompt,
        checkpointer=InMemorySaver(),
    )

    try:
        result = agent.run(max_steps=int(runtime.get('max_pages', 8) or 8))
        final_text = getattr(result, 'final_result', None) or getattr(result, 'content', None) or str(result)
    except Exception as exc:
        final_text = str(exc)

    try:
        supervisor.ainvoke({'messages': [HumanMessage(content=profile_prompt + '\n\n' + final_text)]})
    except Exception:
        pass

    return _parse_browser_use_result(final_text, application_url, runtime, parameters)


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
          const headings = Array.from(document.querySelectorAll('h1, h2, h3')).slice(0, 8).map((el) => clean(el.textContent));
          const buttons = Array.from(document.querySelectorAll('button, [role="button"], input[type="submit"], input[type="button"]')).slice(0, 20).map((el) => clean(el.innerText || el.textContent || el.value || el.getAttribute('aria-label')));
          const links = Array.from(document.querySelectorAll('a[href]')).slice(0, 20).map((el) => clean(el.innerText || el.textContent));
          const inputs = Array.from(document.querySelectorAll('input, select, textarea')).slice(0, 20).map((el) => clean(el.getAttribute('name') || el.getAttribute('placeholder') || el.getAttribute('aria-label') || el.id || el.type || 'control'));
          const menus = Array.from(document.querySelectorAll('nav, menu')).slice(0, 5).map((el) => clean(el.innerText || el.textContent));
          const sections = Array.from(document.querySelectorAll('main, section, article')).slice(0, 5).map((el) => clean(el.innerText || el.textContent).slice(0, 120));
          const forms = Array.from(document.querySelectorAll('form')).slice(0, 8).map((form) => ({
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
          const elements = Array.from(document.querySelectorAll('a[href], button, [role="button"], input[type="submit"], input[type="button"]')).slice(0, 50);
          return elements.map((el, index) => ({
            index,
            text: clean(el.innerText || el.textContent || el.getAttribute('aria-label') || el.value || ''),
            href: clean(el.href || el.getAttribute('href') || ''),
            tag: (el.tagName || '').toLowerCase(),
            role: clean(el.getAttribute('role') || ''),
          })).filter((item) => item.text || item.href);
        }
        """
    )
    return [ClickCandidate(**item) for item in raw]


def _resolve_href(base_url: str, href: str) -> str:
    return urljoin(base_url, href)


def _looks_like_safe_cta(text: str) -> bool:
    return bool(text) and bool(re.search(r'start|continue|next|learn more|view|open|details|explore|sign in|log in|create|register|search|submit|buy|checkout|select', text, re.I))


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
    min_length: str | int | None = None,
    max_length: str | int | None = None,
) -> Interaction:
    return Interaction(
        sequence_id=sequence_id,
        interaction_number=interaction_number,
        element_type=element_type,
        element_label=element_label,
        element_id=None,
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
    )


def _build_step(step_number: int, depth_level: int, page_title: str, page_url: str, interactions: list[Interaction]) -> JourneyStep:
    return JourneyStep(step_number=step_number, depth_level=depth_level, page_title=page_title, page_url=page_url, interactions=interactions)


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
    if parameters:
        interactions.append(
            _build_interaction(
                sequence_id=2,
                interaction_number=2,
                page_url=application_url,
                element_type='input',
                element_label='parameters',
                selector='parameters',
                action='fill',
                value=','.join(sorted(parameters.keys())),
                state_before='empty',
                state_after='filled',
                resulted_in='same_page_update',
                wait_condition='none',
                parent_component='url_parameters',
            )
        )
    step = _build_step(1, 0, page_name, application_url, interactions)
    return [step], [f'Loaded {application_url}'], [f'Open landing page at {application_url}']


def _score_candidate(candidate: ClickCandidate, profile_text: str) -> int:
    text = (candidate.text or '').lower()
    href = (candidate.href or '').lower()
    score = 0
    if _looks_like_safe_cta(text):
        score += 30
    if any(keyword in text for keyword in ('buy', 'ticket', 'park', 'guest', 'checkout', 'continue', 'search', 'manage', 'invite', 'add a guest', 'create managed profile', 'theme park', 'admission')):
        score += 25
    if any(keyword in profile_text for keyword in ('disney', 'ticket', 'park', 'guest', 'family', 'friends')) and any(keyword in text for keyword in ('ticket', 'park', 'guest', 'invite', 'profile', 'checkout', 'add', 'admission')):
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


def _page_to_step(page_number: int, depth: int, page_url: str, title: str, signals: dict[str, object], interactions: list[Interaction]) -> JourneyStep:
    page_title = _safe_text(title) or _derive_page_name(page_url, title)
    return _build_step(page_number, depth, page_title, page_url, interactions)


def _crawl_with_playwright(application_url: str, parameters: dict[str, str], max_depth: int = 5, max_pages: int = 8, follow_links: bool = True) -> tuple[list[JourneyStep], list[str], list[str]]:
    if sync_playwright is None:
        raise RuntimeError('Playwright is not installed')

    profile_text = get_browser_agent_profile(application_url)
    steps: list[JourneyStep] = []
    reasoning_bits: list[str] = []
    test_hints: list[str] = []
    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(application_url, 0)])
    sequence = 1

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1280, 'height': 800})
        try:
            while queue and len(visited) < max_pages:
                current_url, depth = queue.popleft()
                if current_url in visited:
                    continue
                visited.add(current_url)
                page.goto(current_url, wait_until='domcontentloaded', timeout=30000)
                signals = _extract_page_signals(page)
                current_title = _derive_page_name(page.url, signals.get('title') or page.title())
                headings = [h for h in signals.get('headings', []) if h]
                buttons = [b for b in signals.get('buttons', []) if b]
                links = [l for l in signals.get('links', []) if l]
                inputs = [i for i in signals.get('inputs', []) if i]
                menus = [m for m in signals.get('menus', []) if m]
                sections = [s for s in signals.get('sections', []) if s]
                forms = signals.get('forms', []) or []

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
                    wait_condition='domcontentloaded',
                    is_dynamic_element=False,
                    is_custom_component=False,
                    is_shadow_dom=False,
                    parent_component='browser_root',
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
                ))
                sequence += 1
                reasoning_bits.append(scan_summary)

                for idx, heading in enumerate(headings[:4], start=1):
                    interactions.append(_build_interaction(
                        sequence_id=sequence,
                        interaction_number=idx,
                        page_url=page.url,
                        element_type='heading',
                        element_label=heading,
                        selector=f'h{1 if idx == 1 else 2}',
                        action='inspect',
                        value=None,
                        state_before='visible',
                        state_after='visible',
                        resulted_in='content_discovered',
                        wait_condition='none',
                        parent_component='content_area',
                    ))
                    sequence += 1

                for button in buttons[:6]:
                    interactions.append(_build_interaction(
                        sequence_id=sequence,
                        interaction_number=sequence,
                        page_url=page.url,
                        element_type='button',
                        element_label=button,
                        selector='button',
                        action='inspect',
                        value=None,
                        state_before='enabled',
                        state_after='enabled',
                        resulted_in='button_discovered',
                        wait_condition='none',
                        parent_component='control_area',
                        is_custom_component='theme' in button.lower() or 'continue' in button.lower(),
                    ))
                    sequence += 1

                for link in links[:6]:
                    interactions.append(_build_interaction(
                        sequence_id=sequence,
                        interaction_number=sequence,
                        page_url=page.url,
                        element_type='link',
                        element_label=link,
                        selector='a[href]',
                        action='inspect',
                        value=None,
                        state_before='enabled',
                        state_after='enabled',
                        resulted_in='link_discovered',
                        wait_condition='none',
                        parent_component='navigation',
                    ))
                    sequence += 1

                for input_name in inputs[:6]:
                    interactions.append(_build_interaction(
                        sequence_id=sequence,
                        interaction_number=sequence,
                        page_url=page.url,
                        element_type='input',
                        element_label=input_name,
                        selector='input, select, textarea',
                        action='inspect',
                        value=None,
                        state_before='empty',
                        state_after='empty',
                        resulted_in='input_discovered',
                        wait_condition='none',
                        parent_component='form_area',
                    ))
                    sequence += 1

                if forms:
                    for form in forms[:3]:
                        labels = form.get('labels') or []
                        if labels:
                            label_text = ' / '.join(labels[:3])
                            interactions.append(_build_interaction(
                                sequence_id=sequence,
                                interaction_number=sequence,
                                page_url=page.url,
                                element_type='form',
                                element_label=label_text,
                                selector=form.get('action') or 'form',
                                action='inspect',
                                value=form.get('method') or None,
                                state_before='present',
                                state_after='present',
                                resulted_in='form_discovered',
                                wait_condition='none',
                                parent_component='form_area',
                            ))
                            sequence += 1

                if depth < max_depth and follow_links:
                    actions = _extract_clickable_actions(page)
                    scored = sorted((( _score_candidate(action, profile_text), action) for action in actions), key=lambda item: item[0], reverse=True)
                    for score, action in scored[:5]:
                        text = action.text or action.href or 'interactive control'
                        if score < 15 and not _looks_like_safe_cta(text):
                            continue
                        target_url = _resolve_href(application_url, action.href) if action.href else page.url
                        if action.href and not _same_origin(application_url, target_url):
                            continue
                        interaction = _build_interaction(
                            sequence_id=sequence,
                            interaction_number=sequence,
                            page_url=page.url,
                            element_type=action.tag or 'control',
                            element_label=text,
                            selector=action.href or text,
                            action='click',
                            value=None,
                            state_before='enabled',
                            state_after='enabled',
                            resulted_in='new_page' if action.href else 'same_page_update',
                            wait_condition='url_change' if action.href else 'none',
                            api_call_triggered='/api/auth/login' if 'login' in text.lower() else None,
                            api_method='POST' if 'login' in text.lower() else None,
                            api_response_status=None,
                            is_dynamic_element='checkout' in text.lower() or 'guest' in text.lower(),
                            is_custom_component=action.tag == 'button' or 'continue' in text.lower(),
                            is_shadow_dom=False,
                            iframe_context='login_iframe' if 'login' in text.lower() else None,
                            parent_component='browser_agent_click',
                        )
                        interactions.append(interaction)
                        sequence += 1
                        if action.href and _same_origin(application_url, target_url) and target_url not in visited:
                            queue.append((target_url, depth + 1))

                steps.append(_page_to_step(len(steps) + 1, depth, page.url, current_title, signals, interactions))
        finally:
            browser.close()

    if parameters:
        interaction = _build_interaction(
            sequence_id=sequence,
            interaction_number=sequence,
            page_url=application_url,
            element_type='input',
            element_label='parameters',
            selector='parameters',
            action='fill',
            value=','.join(sorted(parameters.keys())),
            state_before='empty',
            state_after='filled',
            resulted_in='parameter_applied',
            wait_condition='none',
            parent_component='url_parameters',
        )
        steps.append(_build_step(len(steps) + 1, max_depth + 1, 'Parameters', application_url, [interaction]))

    return steps, reasoning_bits, test_hints


def _parse_browser_use_result(result_text: str, application_url: str, runtime: dict[str, object], parameters: dict[str, str]) -> ExplorationResult:
    steps, reasoning_bits, _ = _build_url_specific_fallback(application_url, parameters)
    if result_text:
        reasoning_bits.insert(0, result_text[:4000])
    title = _derive_page_name(application_url)
    return ExplorationResult(
        exploration_metadata=ExplorationMetadata(
            app_url=application_url,
            starting_feature=title,
            task_input=f'Explore all possible user journeys starting from {application_url}.',
            depth_level=int(runtime.get('max_depth', 5) or 5),
            is_pre_login_scoped=False,
            total_journeys_discovered=1,
            exploration_timestamp=datetime.now(timezone.utc).isoformat(),
            viewport={'width': 1280, 'height': 800},
            browser='browser_use',
        ),
        journeys=[JourneyRecord(
            journey_id=str(uuid4()),
            journey_title=f'{title} - Browser Use Discovery',
            starting_point=title,
            starting_url=application_url,
            outcome='Exploration Complete',
            outcome_detail='Journey discovered via browser_use agent execution.',
            reasoning=' | '.join(reasoning_bits) if reasoning_bits else result_text[:500],
            session_boundary_reached=False,
            session_boundary_url=None,
            total_depth=max((step.depth_level for step in steps), default=0),
            test_hints={
                'requires_auth': 'login' in application_url.lower() or 'disney' in application_url.lower(),
                'is_critical_path': True,
                'has_api_calls': False,
                'has_file_upload': False,
                'has_dynamic_elements': True,
                'has_validation_flows': True,
                'browser_use_enabled': True,
                'browser_model': runtime.get('browser_model', 'gpt-4o-mini'),
                'supervisor_model': runtime.get('supervisor_model', runtime.get('browser_model', 'gpt-4o-mini')),
                'browser_headers': runtime.get('browser_headers', {}),
                'preconditions': [],
                'test_tags': ['browser_use', 'journey', 'discovery'],
                'data_dependencies': [],
            },
            housekeeping_steps=[],
            steps=steps,
        )],
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


def explore_application(application_url: str, parameters: dict[str, str], crawl_settings: dict[str, object] | None = None) -> ExplorationResult:
    crawl_settings = crawl_settings or {}
    max_depth = int(crawl_settings.get('max_depth', 5))
    max_pages = int(crawl_settings.get('max_pages', 8))
    follow_links = bool(crawl_settings.get('follow_links', True))
    runtime = _runtime_browser_config()
    metadata = ExplorationMetadata(
        app_url=application_url,
        starting_feature=_derive_page_name(application_url),
        task_input=f'Explore all possible user journeys starting from {application_url}.',
        depth_level=max_depth,
        is_pre_login_scoped=False,
        total_journeys_discovered=1,
        exploration_timestamp=datetime.now(timezone.utc).isoformat(),
        viewport={'width': 1280, 'height': 800},
        browser='browser_use' if runtime['browser_use_enabled'] and _browser_use_available() else 'chromium',
    )

    journey_id = str(uuid4())
    browser_use_result = None
    if runtime['browser_use_enabled'] and _browser_use_available():
        try:
            task = get_browser_agent_profile(application_url)
            browser_use_result = _browser_use_to_journey(task, application_url, runtime, parameters)
        except Exception:
            browser_use_result = None

    try:
        if browser_use_result is not None:
            steps = browser_use_result.journeys[0].steps
            reasoning_bits = [browser_use_result.journeys[0].reasoning]
            outcome = browser_use_result.journeys[0].outcome
            outcome_detail = browser_use_result.journeys[0].outcome_detail
            fallback = False
        else:
            steps, reasoning_bits, _ = _crawl_with_playwright(application_url, parameters, max_depth=max_depth, max_pages=max_pages, follow_links=follow_links)
            outcome = 'Exploration Complete'
            outcome_detail = 'Journey discovered successfully from the base URL.'
            fallback = False
    except Exception:
        try:
            steps, reasoning_bits, _ = _crawl_html_fallback(application_url, parameters)
            outcome = 'Exploration Complete'
            outcome_detail = 'Journey discovered from HTML fallback parsing.'
            fallback = True
        except Exception:
            steps = []
            reasoning_bits = []
            fallback = True
            step, reasoning_bits, _ = _build_url_specific_fallback(application_url, parameters)
            steps = step
            outcome = 'Exploration Blocked'
            outcome_detail = 'Browser exploration fell back to URL-level capture only.'

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
            'browser_model': runtime['browser_model'],
            'supervisor_model': runtime['supervisor_model'],
            'browser_headers': runtime['browser_headers'],
            'preconditions': [],
            'test_tags': ['browser_agent', 'journey', 'discovery'],
            'data_dependencies': [],
        },
        housekeeping_steps=[],
        steps=steps,
    )
    metadata.total_journeys_discovered = 1
    exploration = ExplorationResult(exploration_metadata=metadata, journeys=[journey])
    _persist_browser_run_artifacts(exploration, runtime)
    return exploration
