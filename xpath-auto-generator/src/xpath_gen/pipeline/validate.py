"""Stage 4: Cross-browser XPath validation."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

from playwright.sync_api import Browser, sync_playwright

from xpath_gen.config import Settings
from xpath_gen.llm.client import LLMClient
from xpath_gen.models import (
    BrowserValidation,
    Confidence,
    NamedLocator,
    ValidationStatus,
    ValidatedLocator,
)

logger = logging.getLogger(__name__)

BROWSER_TYPES = {
    "chromium": "chromium",
    "firefox": "firefox",
    "webkit": "webkit",
}


def _validate_xpath_on_page(page, xpath: str, browser_name: str) -> BrowserValidation:
    try:
        locator = page.locator(f"xpath={xpath}")
        count = locator.count()

        if count == 0:
            return BrowserValidation(
                browser=browser_name, passed=False, element_count=0, error="Not found"
            )
        if count > 1:
            return BrowserValidation(
                browser=browser_name,
                passed=False,
                element_count=count,
                error=f"Ambiguous: {count} matches",
            )
        visible = locator.first.is_visible()
        return BrowserValidation(
            browser=browser_name,
            passed=visible,
            element_count=1,
            error="" if visible else "Element not visible",
        )
    except Exception as exc:
        return BrowserValidation(browser=browser_name, passed=False, error=str(exc)[:200])


def _validate_all_in_browser(
    browser: Browser,
    url: str,
    xpaths: list[str],
    browser_name: str,
    settings: Settings,
) -> list[BrowserValidation]:
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    page.set_default_timeout(settings.page_timeout_ms)
    page.goto(url, wait_until="domcontentloaded", timeout=settings.page_timeout_ms)

    results: list[BrowserValidation] = []
    for xpath in xpaths:
        results.append(_validate_xpath_on_page(page, xpath, browser_name))

    context.close()
    return results


def _validate_xpaths_sync(
    url: str,
    xpaths: list[str],
    browsers: list[str],
    settings: Settings,
) -> dict[str, list[BrowserValidation]]:
    browser_results_map: dict[str, list[BrowserValidation]] = {}
    with sync_playwright() as pw:
        for browser_name in browsers:
            browser_type = BROWSER_TYPES.get(browser_name)
            if not browser_type:
                continue
            launcher = getattr(pw, browser_type)
            browser = launcher.launch(headless=True)
            browser_results_map[browser_name] = _validate_all_in_browser(
                browser, url, xpaths, browser_name, settings
            )
            browser.close()
    return browser_results_map


async def validate_locators(
    locators: list[NamedLocator],
    *,
    url: str,
    page_title: str,
    browsers: list[str],
    settings: Settings,
    llm: LLMClient,
    on_progress: Callable[[str], None] | None = None,
) -> list[ValidatedLocator]:
    """Validate XPaths across browsers with optional LLM repair."""
    validated: list[ValidatedLocator] = []
    total = len(locators)
    xpaths = [loc.xpath for loc in locators]

    browser_results_map = await asyncio.to_thread(
        _validate_xpaths_sync, url, xpaths, browsers, settings
    )

    for idx, locator in enumerate(locators):
        browser_results = [
            browser_results_map[b][idx]
            for b in browsers
            if b in browser_results_map
        ]
        current_xpath = locator.xpath
        current_confidence = locator.confidence
        repair_note = ""
        all_pass = all(r.passed for r in browser_results)
        status = ValidationStatus.VALID if all_pass else ValidationStatus.INVALID

        if not all_pass and settings.openai_api_key:
            failed = [r for r in browser_results if not r.passed]
            error_msg = "; ".join(f"{r.browser}: {r.error}" for r in failed)
            try:
                repair = await llm.repair_xpath(
                    page_title=page_title,
                    element_name=locator.element_name,
                    tag=locator.tag,
                    text=locator.text,
                    failed_xpath=current_xpath,
                    dom_path="",
                    error=error_msg,
                )
                current_xpath = repair.xpath
                current_confidence = Confidence(repair.confidence)
                repair_note = repair.rationale

                repair_results = await asyncio.to_thread(
                    _validate_xpaths_sync, url, [current_xpath], browsers, settings
                )
                browser_results = [
                    repair_results[b][0] for b in browsers if b in repair_results
                ]

                all_pass = all(r.passed for r in browser_results)
                status = ValidationStatus.REPAIRED if all_pass else ValidationStatus.INVALID
            except Exception as exc:
                repair_note = f"Repair failed: {exc}"

        validated.append(
            ValidatedLocator(
                element_id=locator.element_id,
                element_name=locator.element_name,
                xpath=current_xpath,
                confidence=current_confidence,
                rationale=locator.rationale,
                section=locator.section,
                tag=locator.tag,
                text=locator.text,
                discovery_source=locator.discovery_source,
                browser_results=browser_results,
                overall_status=status,
                repair_note=repair_note,
            )
        )

        if on_progress and (idx + 1) % 20 == 0:
            on_progress(f"Validated {idx + 1}/{total} locators")

    if on_progress:
        passed = sum(1 for v in validated if v.overall_pass)
        rate = (passed / total * 100) if total else 0
        on_progress(f"Validation complete: {passed}/{total} passed ({rate:.1f}%)")

    return validated
