"""In-memory job store for async pipeline runs."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import AsyncIterator, Callable

from xpath_gen.models import JobRequest, JobStage, JobState, JobSummary, ProgressEvent
from xpath_gen.pipeline.orchestrator import PipelineOrchestrator


class JobStore:
    def __init__(self, orchestrator: PipelineOrchestrator, ttl_hours: int = 1) -> None:
        self._orchestrator = orchestrator
        self._jobs: dict[str, JobState] = {}
        self._subscribers: dict[str, list[asyncio.Queue[ProgressEvent | None]]] = {}
        self._lock = asyncio.Lock()
        self._ttl = timedelta(hours=ttl_hours)

    async def start_job(self, request: JobRequest) -> str:
        job_id = str(uuid.uuid4())
        summary = JobSummary(job_id=job_id, url=request.url, status=JobStage.PENDING)
        state = JobState(summary=summary)
        async with self._lock:
            self._jobs[job_id] = state
            self._subscribers[job_id] = []

        asyncio.create_task(self._run_job(job_id, request))
        return job_id

    async def _run_job(self, job_id: str, request: JobRequest) -> None:
        def on_progress(event: ProgressEvent) -> None:
            state = self._jobs.get(job_id)
            if state:
                state.events.append(event)
                state.summary.status = event.stage
            self._notify(job_id, event)

        try:
            state = await self._orchestrator.run(
                request, job_id=job_id, on_progress=on_progress
            )
            async with self._lock:
                self._jobs[job_id] = state
        except Exception as exc:
            async with self._lock:
                state = self._jobs.get(job_id)
                if state:
                    state.summary.status = JobStage.FAILED
                    state.summary.error = str(exc)
        finally:
            self._notify(job_id, None)

    def _notify(self, job_id: str, event: ProgressEvent | None) -> None:
        for queue in self._subscribers.get(job_id, []):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    async def get_job(self, job_id: str) -> JobState | None:
        async with self._lock:
            self._purge_expired()
            return self._jobs.get(job_id)

    async def subscribe(self, job_id: str) -> AsyncIterator[ProgressEvent]:
        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        async with self._lock:
            if job_id not in self._subscribers:
                self._subscribers[job_id] = []
            self._subscribers[job_id].append(queue)
            job = self._jobs.get(job_id)
            if job:
                for event in job.events:
                    yield event

        while True:
            event = await queue.get()
            if event is None:
                break
            yield event

    def _purge_expired(self) -> None:
        cutoff = datetime.utcnow() - self._ttl
        expired = [
            jid for jid, state in self._jobs.items() if state.summary.created_at < cutoff
        ]
        for jid in expired:
            del self._jobs[jid]
            self._subscribers.pop(jid, None)
