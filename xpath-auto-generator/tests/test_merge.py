"""Tests for element merge and deduplication."""

from xpath_gen.discovery.merge import discovery_stats, merge_elements
from xpath_gen.models import DiscoverySource, RawElement


def _el(
    tag: str = "button",
    text: str = "Click",
    el_id: str = "",
    source: DiscoverySource = DiscoverySource.STATIC,
    y: float = 0,
) -> RawElement:
    return RawElement(
        element_id=f"el_{tag}_{text}",
        tag=tag,
        text=text,
        element_id_attr=el_id,
        bbox_y=y,
        discovery_source=source,
    )


def test_merge_deduplicates_same_element():
    static = [_el(text="Submit", el_id="submit-btn")]
    discovered = [_el(text="Submit", el_id="submit-btn", source=DiscoverySource.SCROLL)]
    merged = merge_elements(static, discovered)
    assert len(merged) == 1
    assert merged[0].discovery_source == DiscoverySource.STATIC


def test_merge_keeps_unique_discovered():
    static = [_el(text="Login", el_id="login")]
    discovered = [_el(text="Hidden Menu", source=DiscoverySource.HOVER, y=100)]
    merged = merge_elements(static, discovered)
    assert len(merged) == 2


def test_discovery_stats():
    elements = [
        _el(source=DiscoverySource.STATIC),
        _el(text="A", source=DiscoverySource.STATIC),
        _el(text="B", source=DiscoverySource.HOVER),
        _el(text="C", source=DiscoverySource.SCROLL),
    ]
    static, discovered, boost = discovery_stats(elements)
    assert static == 2
    assert discovered == 2
    assert boost == 100.0
