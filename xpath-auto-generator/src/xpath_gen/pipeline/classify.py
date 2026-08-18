"""Stage 2: Section classification."""

from __future__ import annotations

from xpath_gen.config import Settings
from xpath_gen.llm.client import LLMClient
from xpath_gen.models import RawElement, Section
from xpath_gen.pipeline.extract import apply_heuristic_sections


SECTION_VALUES = {s.value for s in Section}


def _to_section(value: str) -> Section:
    mapping = {
        "header": Section.HEADER,
        "navigation": Section.NAVIGATION,
        "nav": Section.NAVIGATION,
        "maincontent": Section.MAIN_CONTENT,
        "main": Section.MAIN_CONTENT,
        "sidebar": Section.SIDEBAR,
        "form": Section.FORM,
        "modal": Section.MODAL,
        "footer": Section.FOOTER,
        "other": Section.OTHER,
    }
    return mapping.get(value.replace(" ", "").lower(), Section.OTHER)


async def classify_sections(
    elements: list[RawElement],
    *,
    page_title: str,
    url: str,
    settings: Settings,
    llm: LLMClient,
) -> dict[str, Section]:
    """Classify elements into page sections using heuristics + LLM."""
    result = apply_heuristic_sections(elements)
    unlabeled = [e for e in elements if e.element_id not in result]

    if unlabeled and settings.openai_api_key:
        llm_results = await llm.batch_classify(
            unlabeled,
            page_title=page_title,
            url=url,
            batch_size=settings.llm_batch_size_classify,
        )
        for element_id, section_name in llm_results.items():
            result[element_id] = _to_section(section_name)

    for el in elements:
        if el.element_id not in result:
            result[el.element_id] = Section.OTHER

    return result
