"""OpenAI client with structured outputs."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from xpath_gen.config import Settings
from xpath_gen.llm import prompts
from xpath_gen.models import (
    GenerateBatchResponse,
    GeneratedLocator,
    RawElement,
    RepairResponse,
    SectionBatchResponse,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: AsyncOpenAI | None = None
        self._semaphore = asyncio.Semaphore(settings.llm_concurrency)

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            if not self.settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY is required for LLM calls")
            self._client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        return self._client

    async def _parse_structured(self, schema: type[T], system: str, user: str) -> T:
        async with self._semaphore:
            response = await self.client.chat.completions.create(
                model=self.settings.openai_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        return schema.model_validate(data)

    @staticmethod
    def _element_summary(el: RawElement) -> dict:
        return {
            "element_id": el.element_id,
            "tag": el.tag,
            "type": el.element_type,
            "text": el.text[:100],
            "aria_label": el.aria_label,
            "id": el.element_id_attr,
            "name": el.name,
            "placeholder": el.placeholder,
            "role": el.role,
            "data_testid": el.data_testid,
            "dom_path": el.dom_path,
            "discovery_source": el.discovery_source.value,
        }

    async def classify_sections(
        self,
        elements: list[RawElement],
        *,
        page_title: str,
        url: str,
    ) -> SectionBatchResponse:
        elements_json = json.dumps([self._element_summary(e) for e in elements], indent=2)
        user = prompts.SECTION_CLASSIFY_USER.format(
            page_title=page_title,
            url=url,
            elements_json=elements_json,
        )
        return await self._parse_structured(
            SectionBatchResponse,
            prompts.SECTION_CLASSIFY_SYSTEM,
            user,
        )

    async def generate_xpaths(
        self,
        elements: list[RawElement],
        *,
        page_title: str,
        url: str,
    ) -> GenerateBatchResponse:
        elements_json = json.dumps([self._element_summary(e) for e in elements], indent=2)
        user = prompts.XPATH_GENERATE_USER.format(
            page_title=page_title,
            url=url,
            elements_json=elements_json,
        )
        return await self._parse_structured(
            GenerateBatchResponse,
            prompts.XPATH_GENERATE_SYSTEM,
            user,
        )

    async def repair_xpath(
        self,
        *,
        page_title: str,
        element_name: str,
        tag: str,
        text: str,
        failed_xpath: str,
        dom_path: str,
        error: str,
    ) -> RepairResponse:
        user = prompts.XPATH_REPAIR_USER.format(
            page_title=page_title,
            element_name=element_name,
            tag=tag,
            text=text[:100],
            failed_xpath=failed_xpath,
            dom_path=dom_path,
            error=error,
        )
        return await self._parse_structured(
            RepairResponse,
            prompts.XPATH_REPAIR_SYSTEM,
            user,
        )

    async def batch_classify(
        self,
        elements: list[RawElement],
        *,
        page_title: str,
        url: str,
        batch_size: int,
    ) -> dict[str, str]:
        results: dict[str, str] = {}
        for i in range(0, len(elements), batch_size):
            batch = elements[i : i + batch_size]
            response = await self.classify_sections(batch, page_title=page_title, url=url)
            for assignment in response.assignments:
                results[assignment.element_id] = assignment.section
        return results

    async def batch_generate(
        self,
        elements: list[RawElement],
        *,
        page_title: str,
        url: str,
        batch_size: int,
    ) -> list[GeneratedLocator]:
        results: list[GeneratedLocator] = []
        for i in range(0, len(elements), batch_size):
            batch = elements[i : i + batch_size]
            response = await self.generate_xpaths(batch, page_title=page_title, url=url)
            results.extend(response.locators)
        return results
