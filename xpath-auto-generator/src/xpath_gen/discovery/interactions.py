"""Hidden element discovery via programmatic interactions."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Callable

from playwright.sync_api import Page

from xpath_gen.models import DiscoverySource, RawElement
from xpath_gen.pipeline.extract_js import EXTRACT_ELEMENTS_JS

if TYPE_CHECKING:
    from xpath_gen.config import Settings

logger = logging.getLogger(__name__)

DANGEROUS_KEYWORDS = re.compile(
    r"\b(pay|purchase|buy now|delete account|confirm order|checkout|submit payment)\b",
    re.IGNORECASE,
)

HOVER_SELECTORS = [
    "[aria-haspopup='true']",
    "[aria-haspopup='menu']",
    ".dropdown",
    ".dropdown-toggle",
    "nav li",
    "[data-toggle='dropdown']",
    "[role='menuitem']",
]

EXPAND_SELECTORS = [
    "[aria-expanded='false']",
    "[role='tab']",
    "details:not([open]) summary",
    ".accordion-button.collapsed",
    "[data-bs-toggle='collapse']",
]


def _parse_elements(payload: dict, source: DiscoverySource) -> list[RawElement]:
    results: list[RawElement] = []
    for item in payload.get("elements", []):
        item.pop("heuristic_section", None)
        results.append(RawElement(**item, discovery_source=source))
    return results


def _extract(page: Page, source: DiscoverySource) -> list[RawElement]:
    payload = page.evaluate(EXTRACT_ELEMENTS_JS)
    return _parse_elements(payload, source)


def _scroll_discovery(
    page: Page,
    on_progress: Callable[[str], None] | None = None,
) -> list[RawElement]:
    found: list[RawElement] = []
    viewport_height = page.evaluate("window.innerHeight")
    scroll_height = page.evaluate("document.body.scrollHeight")
    position = 0
    step = max(int(viewport_height * 0.8), 300)

    while position < scroll_height:
        page.evaluate(f"window.scrollTo(0, {position})")
        page.wait_for_timeout(400)
        batch = _extract(page, DiscoverySource.SCROLL)
        found.extend(batch)
        position += step
        scroll_height = page.evaluate("document.body.scrollHeight")

    page.evaluate("window.scrollTo(0, 0)")
    if on_progress:
        on_progress(f"Scroll discovery captured {len(found)} element snapshots")
    return found


def _hover_discovery(
    page: Page,
    on_progress: Callable[[str], None] | None = None,
) -> list[RawElement]:
    found: list[RawElement] = []
    for selector in HOVER_SELECTORS:
        try:
            locators = page.locator(selector)
            count = locators.count()
            for i in range(min(count, 15)):
                el = locators.nth(i)
                if not el.is_visible():
                    continue
                el.hover(timeout=3000)
                page.wait_for_timeout(350)
                batch = _extract(page, DiscoverySource.HOVER)
                found.extend(batch)
        except Exception as exc:
            logger.debug("Hover discovery skip %s: %s", selector, exc)

    if on_progress:
        on_progress(f"Hover discovery captured {len(found)} element snapshots")
    return found


def _expand_discovery(
    page: Page,
    on_progress: Callable[[str], None] | None = None,
) -> list[RawElement]:
    found: list[RawElement] = []
    for selector in EXPAND_SELECTORS:
        try:
            locators = page.locator(selector)
            count = locators.count()
            for i in range(min(count, 10)):
                el = locators.nth(i)
                if not el.is_visible():
                    continue
                try:
                    el.click(timeout=3000)
                    page.wait_for_timeout(500)
                    batch = _extract(page, DiscoverySource.EXPAND)
                    found.extend(batch)
                except Exception:
                    continue
        except Exception as exc:
            logger.debug("Expand discovery skip %s: %s", selector, exc)

    if on_progress:
        on_progress(f"Expand discovery captured {len(found)} element snapshots")
    return found


def _is_safe_form(page: Page, form_locator) -> bool:
    try:
        action = form_locator.get_attribute("action") or ""
        if action and not action.startswith(("/", "#", page.url.split("/")[2] if "://" in page.url else "")):
            return False
        buttons = form_locator.locator("button, input[type='submit'], [role='button']")
        count = buttons.count()
        for i in range(count):
            text = (buttons.nth(i).inner_text() or "") + (buttons.nth(i).get_attribute("value") or "")
            if DANGEROUS_KEYWORDS.search(text):
                return False
        return True
    except Exception:
        return False


def _form_discovery(
    page: Page,
    on_progress: Callable[[str], None] | None = None,
) -> list[RawElement]:
    found: list[RawElement] = []
    forms = page.locator("form")
    form_count = forms.count()

    for i in range(min(form_count, 3)):
        form = forms.nth(i)
        if not form.is_visible():
            continue
        if not _is_safe_form(page, form):
            continue

        try:
            inputs = form.locator("input, textarea, select")
            input_count = inputs.count()
            for j in range(input_count):
                inp = inputs.nth(j)
                input_type = (inp.get_attribute("type") or "text").lower()
                if input_type in ("hidden", "submit", "button", "file", "image"):
                    continue
                if not inp.is_visible():
                    continue
                if input_type == "email":
                    inp.fill("test@example.com")
                elif input_type == "password":
                    inp.fill("TestPassword123!")
                elif input_type in ("tel", "number"):
                    inp.fill("5551234567")
                else:
                    inp.fill("TestUser")

            submit = form.locator(
                "button[type='submit'], input[type='submit'], button:not([type='button'])"
            ).first
            if submit.count() > 0 and submit.is_visible():
                submit.click(timeout=3000)
                page.wait_for_timeout(800)
                batch = _extract(page, DiscoverySource.FORM)
                found.extend(batch)
        except Exception as exc:
            logger.debug("Form discovery skip form %d: %s", i, exc)

    if on_progress:
        on_progress(f"Form discovery captured {len(found)} element snapshots")
    return found


def run_hidden_discovery(
    page: Page,
    settings: Settings,
    *,
    on_progress: Callable[[str], None] | None = None,
) -> list[RawElement]:
    """Run scroll, hover, expand, and safe form interactions."""
    discovered: list[RawElement] = []

    scroll_results = _scroll_discovery(page, on_progress)
    discovered.extend(scroll_results)

    hover_results = _hover_discovery(page, on_progress)
    discovered.extend(hover_results)

    expand_results = _expand_discovery(page, on_progress)
    discovered.extend(expand_results)

    form_results = _form_discovery(page, on_progress)
    discovered.extend(form_results)

    return discovered
