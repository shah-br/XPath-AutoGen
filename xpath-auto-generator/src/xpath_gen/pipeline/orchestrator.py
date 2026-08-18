"""Pipeline orchestrator — runs all 5 stages."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

from xpath_gen.config import Settings
from xpath_gen.discovery.merge import discovery_stats
from xpath_gen.llm.client import LLMClient
from xpath_gen.models import JobRequest, JobStage, JobState, JobSummary, ProgressEvent
from xpath_gen.pipeline.classify import classify_sections
from xpath_gen.pipeline.export import export_to_excel
from xpath_gen.pipeline.extract import extract_page
from xpath_gen.pipeline.generate import generate_locators
from xpath_gen.pipeline.validate import validate_locators

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.llm = LLMClient(settings)

    async def run(
        self,
        request: JobRequest,
        *,
        job_id: str | None = None,
        on_progress: Callable[[ProgressEvent], None] | None = None,
    ) -> JobState:
        job_id = job_id or str(uuid.uuid4())
        summary = JobSummary(job_id=job_id, url=request.url, status=JobStage.PENDING)
        state = JobState(summary=summary)
        events: list[ProgressEvent] = []

        def emit(stage: JobStage, message: str, pct: int) -> None:
            event = ProgressEvent(stage=stage, message=message, pct=pct)
            events.append(event)
            state.events.append(event)
            if on_progress:
                on_progress(event)

        try:
            # Stage 1: Extract
            summary.status = JobStage.EXTRACTING
            emit(JobStage.EXTRACTING, f"Loading {request.url}...", 5)

            def extract_progress(msg: str) -> None:
                emit(JobStage.EXTRACTING, msg, 15)

            elements, page_title = await extract_page(
                request.url,
                self.settings,
                enable_hidden_discovery=request.enable_hidden_discovery,
                on_progress=extract_progress,
            )
            state.page_title = page_title
            elements = elements[: request.max_elements]
            static_count, discovered_count, boost_pct = discovery_stats(elements)
            emit(
                JobStage.EXTRACTING,
                f"Extracted {len(elements)} elements "
                f"(+{boost_pct:.0f}% from interaction discovery)",
                25,
            )

            # Stage 2: Classify
            summary.status = JobStage.CLASSIFYING
            emit(JobStage.CLASSIFYING, "Classifying page sections...", 30)
            sections = await classify_sections(
                elements,
                page_title=page_title,
                url=request.url,
                settings=self.settings,
                llm=self.llm,
            )
            emit(JobStage.CLASSIFYING, f"Classified {len(sections)} elements", 40)

            # Stage 3: Generate XPaths
            summary.status = JobStage.GENERATING
            emit(JobStage.GENERATING, "Generating XPath locators with LLM...", 45)
            locators = await generate_locators(
                elements,
                sections,
                page_title=page_title,
                url=request.url,
                settings=self.settings,
                llm=self.llm,
            )
            emit(JobStage.GENERATING, f"Generated {len(locators)} XPath locators", 55)

            # Stage 4: Validate
            summary.status = JobStage.VALIDATING
            emit(JobStage.VALIDATING, "Cross-browser validation in progress...", 60)

            def validate_progress(msg: str) -> None:
                emit(JobStage.VALIDATING, msg, 75)

            validated = await validate_locators(
                locators,
                url=request.url,
                page_title=page_title,
                browsers=request.browsers,
                settings=self.settings,
                llm=self.llm,
                on_progress=validate_progress,
            )
            state.locators = validated
            pass_count = sum(1 for v in validated if v.overall_pass)
            pass_rate = (pass_count / len(validated) * 100) if validated else 0.0
            emit(
                JobStage.VALIDATING,
                f"Validation: {pass_count}/{len(validated)} passed ({pass_rate:.1f}%)",
                85,
            )

            # Stage 5: Export
            summary.status = JobStage.EXPORTING
            emit(JobStage.EXPORTING, "Writing Excel report...", 90)
            output_dir = self.settings.output_dir / job_id
            excel_path = output_dir / "locators.xlsx"
            export_to_excel(
                validated,
                url=request.url,
                output_path=excel_path,
                raw_elements=elements,
            )

            summary.status = JobStage.COMPLETED
            summary.total_elements = len(validated)
            summary.pass_count = pass_count
            summary.pass_rate_pct = round(pass_rate, 1)
            summary.static_count = static_count
            summary.discovered_count = discovered_count
            summary.discovery_boost_pct = boost_pct
            summary.excel_path = str(excel_path)
            summary.completed_at = datetime.utcnow()

            emit(JobStage.COMPLETED, f"Done! {pass_rate:.1f}% pass rate. Ready to download.", 100)
            return state

        except Exception as exc:
            logger.exception("Pipeline failed for job %s", job_id)
            summary.status = JobStage.FAILED
            summary.error = str(exc)
            emit(JobStage.FAILED, f"Pipeline failed: {exc}", 100)
            return state
