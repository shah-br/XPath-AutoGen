"""End-to-end pipeline test without OpenAI (fallback mode)."""

import pytest
from pathlib import Path

from xpath_gen.config import Settings
from xpath_gen.models import JobRequest
from xpath_gen.pipeline.orchestrator import PipelineOrchestrator

FIXTURE = Path(__file__).parent / "fixtures" / "sample_page.html"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pipeline_e2e_fallback(tmp_path):
    settings = Settings(
        openai_api_key="",
        max_elements=30,
        enable_hidden_discovery=False,
        output_dir=tmp_path,
    )
    orchestrator = PipelineOrchestrator(settings)
    request = JobRequest(
        url=FIXTURE.as_uri(),
        enable_hidden_discovery=False,
        max_elements=30,
        browsers=["chromium"],
    )
    state = await orchestrator.run(request)

    assert state.summary.status.value == "completed"
    assert state.summary.total_elements >= 5
    assert Path(state.summary.excel_path).exists()
