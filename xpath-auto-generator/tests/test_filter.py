"""Tests for testable element filtering."""

from xpath_gen.models import DiscoverySource, RawElement
from xpath_gen.pipeline.filter import filter_testable_elements, is_testable_element


def _el(**kwargs) -> RawElement:
    defaults = {
        "element_id": "el_1",
        "tag": "button",
        "text": "Submit",
        "is_visible": True,
        "is_enabled": True,
        "bbox_width": 100,
        "bbox_height": 40,
    }
    defaults.update(kwargs)
    return RawElement(**defaults)


def test_keeps_button_with_text():
    assert is_testable_element(_el(tag="button", text="Sign In"))


def test_skips_invisible_element():
    assert not is_testable_element(_el(is_visible=False))


def test_skips_empty_anchor():
    assert not is_testable_element(_el(tag="a", href="#", text=""))


def test_keeps_anchor_with_href_and_text():
    assert is_testable_element(_el(tag="a", href="/about", text="About Us"))


def test_skips_javascript_href():
    assert not is_testable_element(_el(tag="a", href="javascript:void(0)", text="Click"))


def test_skips_hidden_input():
    assert not is_testable_element(_el(tag="input", element_type="hidden", name="csrf"))


def test_keeps_input_with_name():
    assert is_testable_element(_el(tag="input", element_type="email", name="email", text=""))


def test_skips_tiny_element():
    assert not is_testable_element(_el(bbox_width=2, bbox_height=2))


def test_keeps_data_testid():
    assert is_testable_element(_el(tag="div", text="", data_testid="login-form"))


def test_filter_testable_elements():
    elements = [
        _el(text="Good"),
        _el(tag="a", href="#", text=""),
        _el(tag="input", element_type="text", name="q", text=""),
    ]
    filtered = filter_testable_elements(elements)
    assert len(filtered) == 2
