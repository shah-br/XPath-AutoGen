"""Tests for fallback XPath generation."""

from xpath_gen.models import RawElement, Section
from xpath_gen.pipeline.generate import _fallback_name, _fallback_xpath


def test_fallback_xpath_by_id():
    el = RawElement(element_id="1", tag="button", element_id_attr="submit-btn")
    assert _fallback_xpath(el) == "//*[@id='submit-btn']"


def test_fallback_xpath_by_testid():
    el = RawElement(element_id="2", tag="div", data_testid="login-form")
    assert "data-testid" in _fallback_xpath(el)


def test_fallback_name_pascal_case():
    el = RawElement(element_id="3", tag="button", text="sign in now")
    name = _fallback_name(el)
    assert name[0].isupper()
    assert " " not in name
