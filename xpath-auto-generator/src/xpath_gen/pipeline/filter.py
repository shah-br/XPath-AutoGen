"""Filter extracted elements to those relevant for UI test automation."""

from __future__ import annotations

import re

from xpath_gen.models import RawElement

# React/Vue/Ember auto-generated IDs — unstable for locators
_AUTO_ID_RE = re.compile(r"^(:|r|ember|react)[\d\-_a-z]*$", re.IGNORECASE)

# Noise text patterns (cookie banners, empty labels, icon-only placeholders)
_NOISE_TEXT_RE = re.compile(
    r"^(\s|[·•|/\\>\-<]+|click here|read more|learn more|toggle navigation)$",
    re.IGNORECASE,
)

_INTERACTIVE_TAGS = frozenset({"a", "button", "input", "select", "textarea", "summary"})
_INTERACTIVE_ROLES = frozenset(
    {"button", "link", "tab", "menuitem", "checkbox", "radio", "switch", "combobox"}
)
_INPUT_TYPES_SKIP = frozenset({"hidden", "submit", "button", "image", "file"})


def _has_stable_id(el: RawElement) -> bool:
    return bool(el.element_id_attr) and not _AUTO_ID_RE.match(el.element_id_attr)


def _meaningful_text(text: str) -> bool:
    cleaned = " ".join(text.split())
    if len(cleaned) < 2:
        return False
    return not _NOISE_TEXT_RE.match(cleaned)


def _meaningful_href(href: str) -> bool:
    if not href or href == "#":
        return False
    lowered = href.strip().lower()
    return not lowered.startswith("javascript:")


def is_testable_element(el: RawElement) -> bool:
    """Return True if the element is worth generating a UI test locator for."""
    if not el.is_visible or not el.is_enabled:
        return False

    if el.bbox_width < 8 or el.bbox_height < 8:
        return False

    tag = el.tag.lower()
    role = el.role.lower()
    input_type = el.element_type.lower()

    if tag == "input" and input_type in _INPUT_TYPES_SKIP:
        return False

    has_identity = (
        _has_stable_id(el)
        or bool(el.data_testid)
        or bool(el.name)
        or _meaningful_text(el.text)
        or _meaningful_text(el.aria_label)
        or bool(el.placeholder)
    )

    if tag in ("select", "textarea"):
        return True

    if tag == "input" and input_type not in _INPUT_TYPES_SKIP:
        return has_identity or bool(input_type)

    if tag == "button" or role == "button":
        return has_identity

    if tag == "a" or role == "link":
        return has_identity and _meaningful_href(el.href)

    if role in _INTERACTIVE_ROLES:
        return has_identity

    if tag in _INTERACTIVE_TAGS:
        return has_identity

    # data-testid / stable id alone is enough for any tag
    if el.data_testid or _has_stable_id(el):
        return True

    return False


def filter_testable_elements(elements: list[RawElement]) -> list[RawElement]:
    """Keep only elements that are actionable and identifiable for UI testing."""
    return [el for el in elements if is_testable_element(el)]
