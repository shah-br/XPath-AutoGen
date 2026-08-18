"""Merge and deduplicate elements from static and discovery passes."""

from __future__ import annotations

from xpath_gen.models import DiscoverySource, RawElement


def merge_elements(
    static: list[RawElement],
    discovered: list[RawElement],
) -> list[RawElement]:
    """Deduplicate elements, preferring visible static instances."""
    merged: dict[str, RawElement] = {}

    for el in static:
        fp = el.fingerprint()
        merged[fp] = el

    for el in discovered:
        fp = el.fingerprint()
        existing = merged.get(fp)
        if existing is None:
            merged[fp] = el
            continue
        # Prefer static source but keep discovery metadata if newly visible
        if el.is_visible and not existing.is_visible:
            el.discovery_source = el.discovery_source
            merged[fp] = el

    result = list(merged.values())
    result.sort(key=lambda e: (e.bbox_y, e.bbox_x))
    return result


def discovery_stats(elements: list[RawElement]) -> tuple[int, int, float]:
    """Return static count, discovered-only count, and boost percentage."""
    static = sum(1 for e in elements if e.discovery_source == DiscoverySource.STATIC)
    discovered = len(elements) - static
    if static == 0:
        return static, discovered, 0.0
    boost = (discovered / static) * 100
    return static, discovered, round(boost, 1)
