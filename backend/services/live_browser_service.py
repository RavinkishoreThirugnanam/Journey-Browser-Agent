from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from urllib.parse import urlparse, urlunparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from services.live_event_service import clear_events, publish_event


DEFAULT_VIEWPORT = {'width': 1280, 'height': 800}


_LIVE_POINTER_SCRIPT = """({ x, y, label, pulse }) => {
  const root = document.documentElement;
  let pointer = document.getElementById('__browser_agent_pointer__');
  if (!pointer) {
    pointer = document.createElement('div');
    pointer.id = '__browser_agent_pointer__';
    pointer.dataset.browserAgentOverlay = 'true';
    Object.assign(pointer.style, {
      position: 'fixed', zIndex: '2147483647', width: '22px', height: '22px',
      border: '3px solid #ff5a1f', borderRadius: '50%', background: 'rgba(255,255,255,.72)',
      boxShadow: '0 0 0 5px rgba(255,90,31,.22)', pointerEvents: 'none',
      transition: 'left 180ms ease-out, top 180ms ease-out, transform 120ms ease-out',
    });
    root.appendChild(pointer);
  }
  pointer.style.left = `${Math.max(0, x - 11)}px`;
  pointer.style.top = `${Math.max(0, y - 11)}px`;
  pointer.style.transform = pulse ? 'scale(1.65)' : 'scale(1)';
  pointer.title = label || 'Browser agent action';
  if (pulse) setTimeout(() => { pointer.style.transform = 'scale(1)'; }, 220);
} """


def prepare_live_page(page) -> None:
    """Keep the automated tab in front of the noVNC display."""
    try:
        page.bring_to_front()
    except Exception:
        pass


def show_live_pointer(page, coordinates: dict[str, object] | None, label: str = '', *, pulse: bool = False) -> None:
    """Render a non-interactive pointer because CDP mouse input has no X11 cursor."""
    prepare_live_page(page)
    coordinates = coordinates or {}
    x = float(coordinates.get('x', 0) or 0) + float(coordinates.get('width', 0) or 0) / 2
    y = float(coordinates.get('y', 0) or 0) + float(coordinates.get('height', 0) or 0) / 2
    try:
        page.evaluate(_LIVE_POINTER_SCRIPT, {'x': x, 'y': y, 'label': label, 'pulse': pulse})
        page.mouse.move(x, y, steps=10)
        page.wait_for_timeout(320 if pulse else 220)
    except Exception:
        pass


def scroll_live_page(page, target_y: int, label: str = 'Scrolling page') -> None:
    """Scroll in paced increments so movement is visible in the noVNC stream."""
    prepare_live_page(page)
    try:
        start_y = int(page.evaluate("() => Math.round((document.scrollingElement || document.documentElement).scrollTop || window.scrollY || 0)") or 0)
        delta = int(target_y) - start_y
        steps = max(4, min(10, abs(delta) // 120 + 1))
        show_live_pointer(page, {'x': 28, 'y': 72, 'width': 0, 'height': 0}, label)
        for step in range(1, steps + 1):
            next_y = round(start_y + (delta * step / steps))
            page.evaluate("(y) => window.scrollTo({ top: y, behavior: 'auto' })", next_y)
            page.wait_for_timeout(90)
        page.wait_for_timeout(280)
    except Exception:
        page.evaluate("(y) => window.scrollTo({ top: y, behavior: 'auto' })", int(target_y))


def _cdp_candidates() -> list[str]:
    configured = os.environ.get('BROWSER_CDP_URL', 'http://browser-stream:9222').strip()
    candidates = [configured, 'http://browser-stream:9222', 'http://host.docker.internal:9222', 'http://localhost:9222']
    seen: set[str] = set()
    return [candidate for candidate in candidates if candidate and not (candidate in seen or seen.add(candidate))]


def _resolve_cdp_endpoint(cdp_url: str) -> str:
    """Chromium often returns localhost in /json/version; rewrite it for container-to-container access."""
    parsed = urlparse(cdp_url)
    request = urllib.request.Request(
        f'{cdp_url.rstrip("/")}/json/version',
        headers={'Host': '127.0.0.1:9222'},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        metadata = json.loads(response.read().decode('utf-8'))
    websocket_url = metadata.get('webSocketDebuggerUrl')
    if not websocket_url:
        return cdp_url
    ws_parts = urlparse(websocket_url)
    if ws_parts.hostname in {'127.0.0.1', 'localhost'} and parsed.netloc:
        return urlunparse(ws_parts._replace(netloc=parsed.netloc))
    return websocket_url


def _connect_with_retry(playwright, source_url: str, timeout_seconds: int = 35):
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        for cdp_url in _cdp_candidates():
            try:
                endpoint_url = _resolve_cdp_endpoint(cdp_url)
                publish_event(source_url, {
                    'type': 'status',
                    'status': 'Connecting to live browser',
                    'url': source_url,
                    'cdp_url': cdp_url,
                    'endpoint_url': endpoint_url,
                    'sequence': attempt,
                })
                return playwright.chromium.connect_over_cdp(endpoint_url, timeout=7000)
            except Exception as exc:  # pragma: no cover - depends on runtime container state
                last_error = exc
        time.sleep(1)
    raise RuntimeError(f'Unable to connect to browser-stream CDP after {timeout_seconds}s: {last_error}')


def connect_live_browser(playwright, source_url: str, timeout_seconds: int = 35):
    """Public helper used by the browser agent so live preview and crawl share the same CDP path."""
    return _connect_with_retry(playwright, source_url, timeout_seconds)


def _visible_page(browser):
    context = browser.contexts[0] if browser.contexts else browser.new_context(viewport=DEFAULT_VIEWPORT)
    if context.pages:
        # noVNC renders the first browser tab, so navigate that shared tab.
        return context.pages[0]
    return context.new_page()


def navigate_live_browser(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise ValueError('Only valid http or https URLs can be opened in the live browser.')

    clear_events(url)
    publish_event(url, {'type': 'status', 'status': 'Navigating', 'url': url, 'title': 'Opening selected URL'})
    with sync_playwright() as playwright:
        browser = _connect_with_retry(playwright, url)
        page = _visible_page(browser)
        try:
            page.bring_to_front()
        except PlaywrightError:
            pass
        publish_event(url, {'type': 'navigation_started', 'status': 'Navigating', 'url': url, 'title': 'Opening selected URL'})
        response = page.goto(url, wait_until='domcontentloaded', timeout=60000)
        try:
            page.wait_for_load_state('networkidle', timeout=15000)
        except Exception:
            # Modern SPAs often keep long-polling/network connections open. DOM ready is enough for the live preview.
            pass
        page.wait_for_timeout(1000)
        title = page.title()
        result = {
            'url': page.url,
            'title': title,
            'status': 'Live browser navigated',
            'http_status': str(response.status) if response else '',
        }
        publish_event(url, {
            'type': 'page_loaded',
            'status': 'Waiting',
            'url': page.url,
            'title': title,
            'http_status': result['http_status'],
        })
        return result


_replay_lock = threading.Lock()


def _replay_locator(page, interaction: dict):
    selector = str(interaction.get('replay_selector') or interaction.get('selector') or '').strip()
    if selector and selector not in {'document.querySelectorAll'}:
        try:
            locator = page.locator(selector).first
            if locator.count():
                return locator
        except Exception:
            pass
    element_id = str(interaction.get('element_id') or '').strip()
    if element_id:
        locator = page.locator(f'#{element_id}').first
        if locator.count():
            return locator
    label = str(interaction.get('element') or interaction.get('element_label') or '').strip()
    if label:
        locator = page.get_by_text(label, exact=True).first
        if locator.count():
            return locator
    return None


def _publish_replay_event(stream_key: str, interaction: dict, index: int, status: str, event_type: str, result: str = '') -> None:
    publish_event(stream_key, {
        'type': event_type,
        'status': status,
        'sequence': index + 1,
        'recorded_event': index + 1,
        'recorded_action': interaction.get('action') or 'inspect',
        'element': interaction.get('element') or interaction.get('element_label') or interaction.get('selector') or 'Recorded event',
        'selector': interaction.get('replay_selector') or interaction.get('selector') or '',
        'url': interaction.get('page_url') or stream_key,
        'destination_url': interaction.get('destination_url') or '',
        'coordinates': interaction.get('coordinates') or {},
        'result': result,
    })


def _run_live_replay(stream_key: str, interactions: list[dict]) -> None:
    try:
        clear_events(stream_key)
        publish_event(stream_key, {'type': 'replay_started', 'status': 'Recorded replay started', 'url': stream_key, 'event_count': len(interactions)})
        with sync_playwright() as playwright:
            browser = _connect_with_retry(playwright, stream_key)
            page = _visible_page(browser)
            page.bring_to_front()
            page.goto(stream_key, wait_until='domcontentloaded', timeout=60000)
            page.wait_for_timeout(700)
            for index, interaction in enumerate(interactions):
                if not isinstance(interaction, dict):
                    continue
                action = str(interaction.get('action') or '').lower()
                _publish_replay_event(stream_key, interaction, index, 'Replaying', 'replay_event_started')
                selector = str(interaction.get('replay_selector') or interaction.get('selector') or '').strip()
                try:
                    if action in {'open', 'navigate'}:
                        target = selector or str(interaction.get('page_url') or stream_key)
                        if target.startswith(('http://', 'https://')):
                            page.goto(target, wait_until='domcontentloaded', timeout=60000)
                            page.wait_for_timeout(700)
                    elif action in {'click', 'tap', 'submit'}:
                        locator = _replay_locator(page, interaction)
                        if locator:
                            locator.scroll_into_view_if_needed(timeout=5000)
                            box = locator.bounding_box()
                            coordinates = {'x': box['x'], 'y': box['y'], 'width': box['width'], 'height': box['height']} if box else interaction.get('coordinates') or {}
                            show_live_pointer(page, coordinates, str(interaction.get('element') or interaction.get('element_label') or 'Click'), pulse=True)
                            locator.click(timeout=10000, no_wait_after=True)
                            page.wait_for_timeout(450)
                        else:
                            coordinates = interaction.get('coordinates') or {}
                            if coordinates.get('x') is None or coordinates.get('y') is None:
                                raise RuntimeError(f'No replayable selector for {selector or "recorded click"}')
                            show_live_pointer(page, coordinates, str(interaction.get('element') or interaction.get('element_label') or 'Click'), pulse=True)
                            page.mouse.click(float(coordinates['x']), float(coordinates['y']))
                            page.wait_for_timeout(450)
                        try:
                            page.wait_for_load_state('domcontentloaded', timeout=8000)
                        except Exception:
                            pass
                        page.wait_for_timeout(700)
                    elif action in {'fill', 'type', 'input'}:
                        locator = _replay_locator(page, interaction)
                        if not locator:
                            raise RuntimeError(f'No replayable input selector for {selector or "recorded input"}')
                        locator.fill(str(interaction.get('value') or ''), timeout=10000)
                    elif action == 'select':
                        locator = _replay_locator(page, interaction)
                        if not locator:
                            raise RuntimeError(f'No replayable select selector for {selector or "recorded select"}')
                        locator.select_option(str(interaction.get('value') or ''), timeout=10000)
                    elif action == 'hover':
                        locator = _replay_locator(page, interaction)
                        if locator:
                            locator.scroll_into_view_if_needed(timeout=5000)
                            box = locator.bounding_box()
                            coordinates = {'x': box['x'], 'y': box['y'], 'width': box['width'], 'height': box['height']} if box else interaction.get('coordinates') or {}
                            show_live_pointer(page, coordinates, str(interaction.get('element') or interaction.get('element_label') or 'Hover'))
                            locator.hover(timeout=10000)
                            page.wait_for_timeout(650)
                    elif action == 'scroll':
                        coordinates = interaction.get('coordinates') or {}
                        raw_target = interaction.get('value')
                        target_y = int(float(raw_target)) if raw_target not in (None, '') else int(float(coordinates.get('y', 0) or 0))
                        scroll_live_page(page, target_y, str(interaction.get('element') or interaction.get('element_label') or 'Scrolling page'))
                    _publish_replay_event(stream_key, interaction, index, 'Recorded action complete', 'replay_event_completed', 'replayed')
                except Exception as exc:
                    _publish_replay_event(stream_key, interaction, index, 'Replay action failed', 'replay_event_failed', f'{type(exc).__name__}: {exc}')
            publish_event(stream_key, {'type': 'replay_completed', 'status': 'Recorded replay complete', 'url': page.url, 'event_count': len(interactions)})
    except Exception as exc:
        publish_event(stream_key, {'type': 'replay_failed', 'status': 'Recorded replay unavailable', 'url': stream_key, 'result': f'{type(exc).__name__}: {exc}'})
    finally:
        _replay_lock.release()


def replay_live_browser(url: str, interactions: list[dict]) -> dict[str, object]:
    if not _replay_lock.acquire(blocking=False):
        raise RuntimeError('A live browser replay is already running.')
    threading.Thread(target=_run_live_replay, args=(url, interactions), daemon=True).start()
    return {'status': 'Recorded replay started', 'event_count': len(interactions)}