"""Stage 1: DOM extraction via Playwright."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Callable

from playwright.sync_api import sync_playwright

from xpath_gen.discovery.interactions import run_hidden_discovery
from xpath_gen.discovery.merge import merge_elements
from xpath_gen.models import DiscoverySource, RawElement, Section
from xpath_gen.pipeline.extract_js import EXTRACT_ELEMENTS_JS
from xpath_gen.pipeline.filter import filter_testable_elements

if TYPE_CHECKING:
    from xpath_gen.config import Settings

logger = logging.getLogger(__name__)

VIEWPORT = {"width": 1280, "height": 800}


def _parse_raw_elements(
    payload: dict,
    source: DiscoverySource = DiscoverySource.STATIC,
) -> tuple[list[RawElement], dict[str, str]]:
    elements: list[RawElement] = []
    heuristics: dict[str, str] = {}
    for item in payload.get("elements", []):
        heuristic = item.pop("heuristic_section", "")
        el = RawElement(**item, discovery_source=source)
        elements.append(el)
        if heuristic:
            heuristics[el.element_id] = heuristic
    return elements, heuristics


def _extract_page_sync(
    url: str,
    settings: Settings,
    *,
    enable_hidden_discovery: bool = True,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[list[RawElement], str]:
    """Extract interactive elements from a URL (sync — runs in a worker thread)."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport=VIEWPORT)
        page = context.new_page()
        page.set_default_timeout(settings.page_timeout_ms)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=settings.page_timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                logger.debug("networkidle timeout for %s, continuing", url)

            static_payload = page.evaluate(EXTRACT_ELEMENTS_JS)
            static_elements, heuristics = _parse_raw_elements(
                static_payload, DiscoverySource.STATIC
            )
            for el in static_elements:
                if el.element_id in heuristics:
                    el.__dict__["_heuristic_section"] = heuristics[el.element_id]
            page_title = static_payload.get("title", "")

            if on_progress:
                on_progress(f"Static extraction found {len(static_elements)} elements")

            discovered: list[RawElement] = []
            if enable_hidden_discovery and settings.enable_hidden_discovery:
                discovered = run_hidden_discovery(page, settings, on_progress=on_progress)

            merged = merge_elements(static_elements, discovered)
            filtered = filter_testable_elements(merged)
            if on_progress:
                on_progress(
                    f"Merged {len(merged)} elements, kept {len(filtered)} testable "
                    f"({len(discovered)} from interaction discovery)"
                )

            return filtered[: settings.max_elements], page_title
        finally:
            context.close()
            browser.close()


async def extract_page(
    url: str,
    settings: Settings,
    *,
    enable_hidden_discovery: bool = True,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[list[RawElement], str]:
    """Extract interactive elements from a URL."""
    return await asyncio.to_thread(
        _extract_page_sync,
        url,
        settings,
        enable_hidden_discovery=enable_hidden_discovery,
        on_progress=on_progress,
    )


def apply_heuristic_sections(elements: list[RawElement]) -> dict[str, Section]:
    """Map element_id to heuristic section from DOM landmarks."""
    mapping: dict[str, Section] = {}
    section_map = {
        "Header": Section.HEADER,
        "Navigation": Section.NAVIGATION,
        "MainContent": Section.MAIN_CONTENT,
        "Sidebar": Section.SIDEBAR,
        "Form": Section.FORM,
        "Modal": Section.MODAL,
        "Footer": Section.FOOTER,
    }
    for el in elements:
        heuristic = getattr(el, "_heuristic_section", None) or el.__dict__.get("_heuristic_section")
        if heuristic and heuristic in section_map:
            mapping[el.element_id] = section_map[heuristic]
    return mapping
