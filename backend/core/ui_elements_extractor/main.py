from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from core.config import STORAGE_DIR

DEFAULT_OUTPUT_DIR = STORAGE_DIR / "generated_files"
DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SITE_PATTERNS = {
    "wdw": "disneyworld.disney.go.com",
    "dlr": "disneyland.disney.go.com",
    "dcl": "disneycruise.disney.go.com",
}


def _read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def normalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    full_path = parsed.path
    if parsed.fragment:
        full_path += f"#{parsed.fragment}"
    path = full_path.strip("/").replace("/", "_").replace("-", "_")
    return f"{parsed.netloc}_{path}" if path else parsed.netloc


def extract_urls_by_site(browser_agent_data: dict[str, Any], site_patterns: dict[str, str]) -> dict[str, list[str]]:
    urls_by_site = {site: set() for site in site_patterns}
    journeys = browser_agent_data.get("journeys", []) if isinstance(browser_agent_data, dict) else []
    for journey in journeys:
        for step in journey.get("steps", []) or []:
            url = step.get("page_url")
            if not url:
                continue
            for site, pattern in site_patterns.items():
                if pattern in url:
                    urls_by_site[site].add(url)
                    break
    return {site: sorted(urls) for site, urls in urls_by_site.items()}


def _extract_element_summaries(page) -> list[dict[str, Any]]:
    return page.evaluate(
        """() => {
          const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
          const tags = Array.from(document.querySelectorAll('a, button, input, select, textarea, [role="button"], [role="link"]')).slice(0, 120);
          return tags.map((el, index) => ({
            index,
            tag: (el.tagName || '').toLowerCase(),
            text: clean(el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || el.getAttribute('title')),
            href: clean(el.href || el.getAttribute('href') || ''),
            type: clean(el.getAttribute('type') || ''),
            name: clean(el.getAttribute('name') || ''),
            placeholder: clean(el.getAttribute('placeholder') || ''),
            aria_label: clean(el.getAttribute('aria-label') || ''),
            title: clean(el.getAttribute('title') || ''),
            role: clean(el.getAttribute('role') || ''),
            testid: clean(el.getAttribute('data-testid') || ''),
            disabled: !!el.disabled,
            visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
          }));
        }"""
    )


def extract_page_data(page, url: str, step_number: int) -> tuple[dict[str, Any], Any]:
    html = page.content()
    screenshot_path = DEFAULT_OUTPUT_DIR / f"{normalize_url(url) or 'page'}_{step_number}.png"
    try:
        page.screenshot(path=str(screenshot_path), full_page=True)
    except Exception:
        screenshot_path = None

    elements = _extract_element_summaries(page)
    page_data = {
        "url": url,
        "page": {
            "url": url,
            "step_number": step_number,
            "page_title": page.title(),
            "html_file": None,
            "screenshot": str(screenshot_path) if screenshot_path else None,
            "total_elements": len(elements),
            "elements": elements,
            "html_snippet": html[:25000],
        },
        "modals": [],
    }
    return page_data, page


def get_button(page, button_data: dict[str, Any]):
    selector = button_data.get("selector") or button_data.get("testid") or ""
    if not selector:
        return None
    locator = page.locator(selector)
    if locator.count() <= button_data.get("index", 0):
        return None
    return locator.nth(button_data.get("index", 0))


def process_navigation(page, before_url: str, step: int) -> bool:
    return page.url != before_url


def process_buttons(page, url: str, step: int, page_data: dict[str, Any], buttons: list[dict[str, Any]]):
    for idx, button_data in enumerate(buttons):
        try:
            button = get_button(page, button_data)
            if not button:
                continue
            if hasattr(button, "is_visible") and not button.is_visible():
                continue
            before_url = page.url
            before_html = page.content()
            try:
                button.click(timeout=3000)
            except Exception:
                continue
            if process_navigation(page, before_url, step):
                continue
            if before_html == page.content():
                continue
            page_data["modals"].append(
                {
                    "index": idx,
                    "url": page.url,
                    "before_url": before_url,
                    "source_button": button_data,
                }
            )
        except Exception:
            continue


def process_page(page, url: str, step: int) -> dict[str, Any]:
    page_data, active_frame = extract_page_data(page, url, step)
    buttons = [
        item
        for item in page_data["page"]["elements"]
        if item.get("tag") in {"button", "a"} or item.get("role") == "button"
    ]
    process_buttons(page, url, step, page_data, buttons)
    return page_data


def build_ui_elements(browser_agent_json: dict[str, Any], output_pages_dir: Path | None = None) -> list[dict[str, Any]]:
    ui_elements: list[dict[str, Any]] = []
    output_pages_dir = output_pages_dir or (DEFAULT_OUTPUT_DIR / "ui_pages")
    output_pages_dir.mkdir(parents=True, exist_ok=True)
    for journey in browser_agent_json.get("journeys", []) or []:
        for step in journey.get("steps", []) or []:
            page_url = step.get("page_url")
            if not page_url:
                continue
            file_name = f"{normalize_url(page_url) or 'page'}.json"
            file_path = output_pages_dir / file_name
            extracted = _read_json(file_path)
            ui_elements.append(
                {
                    "page_url": page_url,
                    "source_file": file_name if file_path.exists() else None,
                    "is_login_flow_context": any(
                        "login" in (interaction.get("parent_component", "") or "").lower()
                        for interaction in step.get("interactions", []) or []
                    ),
                    "extracted_url_ui_elements": extracted,
                }
            )
    return ui_elements


def run_ui_elements_pipeline(input_journey_file: str, site: str = "wdw") -> str | None:
    input_path = Path(input_journey_file)
    browser_agent_json = _read_json(input_path)
    if not browser_agent_json:
        return None

    urls_by_site = extract_urls_by_site(browser_agent_json, SITE_PATTERNS)
    site_urls = urls_by_site.get(site, [])
    output_pages_dir = DEFAULT_OUTPUT_DIR / "ui_pages" / site
    output_pages_dir.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()
            try:
                for step, url in enumerate(site_urls, start=1):
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        page_data = process_page(page, url, step)
                        _write_json(output_pages_dir / f"{normalize_url(url)}.json", page_data)
                    except Exception as exc:
                        _write_json(output_pages_dir / f"{normalize_url(url)}.json", {"url": url, "error": str(exc)})
            finally:
                try:
                    context.close()
                except Exception:
                    pass
                try:
                    browser.close()
                except Exception:
                    pass
    except Exception as exc:
        _write_json(output_pages_dir / "cdp_error.json", {"error": str(exc)})

    final_output = {
        "browser_agent_section": {
            "_comment": "Browser Agent JSON",
            "browser_agent_data": browser_agent_json,
        },
        "page_url_ui_element_section": {
            "_comment": "Page URL UI Element JSON",
            "ui_elements_data": build_ui_elements(browser_agent_json, output_pages_dir=output_pages_dir),
        },
    }
    combined_path = DEFAULT_OUTPUT_DIR / f"combined_{input_path.stem}.json"
    _write_json(combined_path, final_output)
    return str(combined_path)
