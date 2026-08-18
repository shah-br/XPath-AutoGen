"""FastAPI web application."""

from __future__ import annotations

import xpath_gen.playwright_compat  # noqa: F401 — Windows event loop policy

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from xpath_gen.config import get_settings
from xpath_gen.models import JobRequest, JobStage
from xpath_gen.pipeline.orchestrator import PipelineOrchestrator
from xpath_gen.web.jobs import JobStore

BASE_DIR = Path(__file__).resolve().parent
settings = get_settings()
orchestrator = PipelineOrchestrator(settings)
job_store = JobStore(orchestrator)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="XPath Auto Generator",
    description="LLM-powered XPath locator extraction pipeline",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "has_api_key": bool(settings.openai_api_key),
        },
    )


@app.post("/api/jobs")
async def create_job(request: JobRequest) -> dict:
    if not request.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")
    job_id = await job_store.start_job(request)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = await job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job.summary.job_id,
        "url": job.summary.url,
        "status": job.summary.status.value,
        "total_elements": job.summary.total_elements,
        "pass_count": job.summary.pass_count,
        "pass_rate_pct": job.summary.pass_rate_pct,
        "static_count": job.summary.static_count,
        "discovered_count": job.summary.discovered_count,
        "discovery_boost_pct": job.summary.discovery_boost_pct,
        "error": job.summary.error,
        "completed": job.summary.status in (JobStage.COMPLETED, JobStage.FAILED),
    }


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str) -> StreamingResponse:
    job = await job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_stream():
        async for event in job_store.subscribe(job_id):
            payload = {
                "stage": event.stage.value,
                "message": event.message,
                "pct": event.pct,
            }
            yield f"data: {json.dumps(payload)}\n\n"

        job_state = await job_store.get_job(job_id)
        if job_state and job_state.summary.status == JobStage.COMPLETED:
            done = {
                "stage": "completed",
                "message": "Pipeline finished",
                "pct": 100,
                "summary": {
                    "total_elements": job_state.summary.total_elements,
                    "pass_rate_pct": job_state.summary.pass_rate_pct,
                    "discovery_boost_pct": job_state.summary.discovery_boost_pct,
                },
            }
            yield f"data: {json.dumps(done)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/jobs/{job_id}/download")
async def download_excel(job_id: str) -> FileResponse:
    job = await job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.summary.status != JobStage.COMPLETED:
        raise HTTPException(status_code=400, detail="Job not completed yet")
    if not job.summary.excel_path:
        raise HTTPException(status_code=404, detail="Excel file not found")

    path = Path(job.summary.excel_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Excel file missing on disk")

    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="locators.xlsx",
    )
