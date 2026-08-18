"""Integration test for DOM extraction against local fixture."""

import pytest
from pathlib import Path

from xpath_gen.config import Settings
from xpath_gen.pipeline.extract import extract_page


FIXTURE = Path(__file__).parent / "fixtures" / "sample_page.html"
FIXTURE_URL = FIXTURE.as_uri()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_extract_sample_page():
    settings = Settings(max_elements=50, enable_hidden_discovery=False)
    elements, title = await extract_page(
        FIXTURE_URL,
        settings,
        enable_hidden_discovery=False,
    )
    assert title == "Sample Test Page"
    assert len(elements) >= 5
    tags = {e.tag for e in elements}
    assert "button" in tags
    assert "a" in tags or "input" in tags
