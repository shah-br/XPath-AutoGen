"""Stage 3: LLM XPath generation."""

from __future__ import annotations

from xpath_gen.config import Settings
from xpath_gen.llm.client import LLMClient
from xpath_gen.models import Confidence, NamedLocator, RawElement, Section


def _xpath_literal(value: str) -> str:
    """Escape a string for use inside an XPath string literal."""
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    return "concat(" + ", \"'\", ".join(f"'{part}'" for part in parts) + ")"


def _fallback_xpath(el: RawElement) -> str:
    """Generate a basic XPath when LLM is unavailable."""
    if el.element_id_attr and not el.element_id_attr.startswith(":"):
        return f"//*[@id={_xpath_literal(el.element_id_attr)}]"
    if el.data_testid:
        return f"//*[@data-testid={_xpath_literal(el.data_testid)}]"
    if el.name:
        return f"//{el.tag}[@name={_xpath_literal(el.name)}]"
    if el.aria_label:
        return f"//*[@aria-label={_xpath_literal(el.aria_label)}]"
    if el.placeholder:
        return f"//{el.tag}[@placeholder={_xpath_literal(el.placeholder)}]"
    if el.text and len(el.text.strip()) <= 80:
        text = el.text.strip()
        if len(text) <= 40:
            return f"//{el.tag}[normalize-space()={_xpath_literal(text)}]"
        return f"//{el.tag}[contains(normalize-space(), {_xpath_literal(text[:40])})]"
    if el.href and el.tag == "a":
        return f"//a[@href={_xpath_literal(el.href)}]"
    if el.dom_path:
        parts = []
        for segment in el.dom_path.split(" > "):
            segment = segment.strip()
            if not segment:
                continue
            if "#" in segment:
                tag, id_part = segment.split("#", 1)
                tag = tag or "*"
                parts.append(f"{tag}[@id={_xpath_literal(id_part)}]")
            elif "." in segment:
                tag, cls = segment.split(".", 1)
                tag = tag or "*"
                cls_name = cls.split(".")[0]
                parts.append(f"{tag}[contains(@class, {_xpath_literal(cls_name)})]")
            else:
                parts.append(segment)
        if parts:
            return "//" + "/".join(parts)
    return f"(//{el.tag})[1]"


def _fallback_name(el: RawElement) -> str:
    base = el.aria_label or el.text or el.name or el.placeholder or el.tag
    cleaned = "".join(c if c.isalnum() else " " for c in base).title().replace(" ", "")
    return (cleaned or "Element")[:40]


async def generate_locators(
    elements: list[RawElement],
    sections: dict[str, Section],
    *,
    page_title: str,
    url: str,
    settings: Settings,
    llm: LLMClient,
) -> list[NamedLocator]:
    """Generate named XPath locators for all elements."""
    locators: list[NamedLocator] = []

    if settings.openai_api_key:
        generated = await llm.batch_generate(
            elements,
            page_title=page_title,
            url=url,
            batch_size=settings.llm_batch_size_generate,
        )
        by_id = {g.element_id: g for g in generated}
    else:
        by_id = {}

    for el in elements:
        gen = by_id.get(el.element_id)
        if gen:
            locators.append(
                NamedLocator(
                    element_id=el.element_id,
                    element_name=gen.element_name,
                    xpath=gen.xpath,
                    confidence=Confidence(gen.confidence),
                    rationale=gen.rationale,
                    section=sections.get(el.element_id, Section.OTHER),
                    tag=el.tag,
                    text=el.text,
                    discovery_source=el.discovery_source,
                )
            )
        else:
            locators.append(
                NamedLocator(
                    element_id=el.element_id,
                    element_name=_fallback_name(el),
                    xpath=_fallback_xpath(el),
                    confidence=Confidence.LOW,
                    rationale="Fallback heuristic XPath (no API key or LLM miss)",
                    section=sections.get(el.element_id, Section.OTHER),
                    tag=el.tag,
                    text=el.text,
                    discovery_source=el.discovery_source,
                )
            )

    return locators
