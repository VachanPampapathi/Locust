from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Response, status
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
)
from prometheus_client.exposition import generate_latest
from pydantic import BaseModel, Field

from perf_framework.config import Settings, load_settings


class DatasetRequest(BaseModel):
    name: str


class JobRequest(BaseModel):
    tenantId: str
    datasetId: str
    jobType: str
    jobName: str
    options: dict[str, object] = Field(default_factory=dict)


@dataclass
class JobRecord:
    job_id: str
    tenant_id: str
    tenant_group: str
    dataset_id: str
    job_type: str
    job_name: str
    status: Literal["QUEUED", "RUNNING", "COMPLETED"]
    queued_at: float
    started_at: float | None = None
    completed_at: float | None = None


class SimulatorMetrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.submitted = Counter(
            "simulator_jobs_submitted_total",
            "Jobs accepted by the simulator",
            ("tenant_group", "job_type"),
            registry=self.registry,
        )
        self.completed = Counter(
            "simulator_jobs_completed_total",
            "Jobs completed by the simulator",
            ("tenant_group", "job_type"),
            registry=self.registry,
        )
        self.queue_wait = Histogram(
            "simulator_job_queue_wait_seconds",
            "Time a job spent queued",
            ("tenant_group", "job_type"),
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
            registry=self.registry,
        )
        self.running = Gauge(
            "simulator_running_jobs",
            "Current running jobs",
            registry=self.registry,
        )
        self.queued = Gauge(
            "simulator_queue_depth",
            "Current queued jobs",
            registry=self.registry,
        )
        self.max_running = Gauge(
            "simulator_max_running_jobs",
            "Maximum simultaneously running jobs observed since reset",
            registry=self.registry,
        )
        self.max_queue = Gauge(
            "simulator_max_queue_depth",
            "Maximum queue depth observed since reset",
            registry=self.registry,
        )

    def reset(self) -> None:
        self.submitted.clear()
        self.completed.clear()
        self.queue_wait.clear()
        self.running.set(0)
        self.queued.set(0)
        self.max_running.set(0)
        self.max_queue.set(0)


class SimulatorState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.datasets: dict[str, dict[str, str]] = {}
        self.jobs: dict[str, JobRecord] = {}
        self.queue: deque[str] = deque()
        self.lock = asyncio.Lock()
        self.metrics = SimulatorMetrics()
        self.max_running_observed = 0
        self.max_queue_observed = 0

    @property
    def running_limit(self) -> int:
        physical = self.settings.simulator.physical_capacity
        if len(self.settings.job_types) > 1:
            return min(physical, self.settings.simulator.mixed_job_limit)
        return physical

    async def create_dataset(self, name: str, tenant_id: str) -> str:
        dataset_id = f"dataset-{uuid4().hex[:12]}"
        async with self.lock:
            self.datasets[dataset_id] = {"name": name, "tenantId": tenant_id}
        return dataset_id

    async def submit_job(self, request: JobRequest, tenant_group: str) -> JobRecord:
        async with self.lock:
            if request.datasetId not in self.datasets:
                raise HTTPException(status_code=400, detail="unknown datasetId")
            if self.datasets[request.datasetId]["tenantId"] != request.tenantId:
                raise HTTPException(
                    status_code=400,
                    detail="dataset tenant does not match job tenant",
                )
            job = JobRecord(
                job_id=f"job-{uuid4().hex[:12]}",
                tenant_id=request.tenantId,
                tenant_group=tenant_group,
                dataset_id=request.datasetId,
                job_type=request.jobType,
                job_name=request.jobName,
                status="QUEUED",
                queued_at=time.monotonic(),
            )
            self.jobs[job.job_id] = job
            self.queue.append(job.job_id)
            self.metrics.submitted.labels(tenant_group, job.job_type).inc()
            self._update_depth_metrics()
            return job

    async def get_job(self, job_id: str) -> JobRecord | None:
        async with self.lock:
            return self.jobs.get(job_id)

    async def reset(self) -> None:
        async with self.lock:
            self.datasets.clear()
            self.jobs.clear()
            self.queue.clear()
            self.max_running_observed = 0
            self.max_queue_observed = 0
            self.metrics.reset()

    async def scheduler(self) -> None:
        try:
            while True:
                await self._tick()
                await asyncio.sleep(self.settings.simulator.scheduler_interval_seconds)
        except asyncio.CancelledError:
            return

    async def _tick(self) -> None:
        now = time.monotonic()
        async with self.lock:
            for job in self.jobs.values():
                if job.status != "RUNNING" or job.started_at is None:
                    continue
                if now - job.started_at >= self._duration_for(job.job_type):
                    job.status = "COMPLETED"
                    job.completed_at = now
                    self.metrics.completed.labels(job.tenant_group, job.job_type).inc()

            running = sum(job.status == "RUNNING" for job in self.jobs.values())
            while self.queue and running < self.running_limit:
                job = self.jobs[self.queue.popleft()]
                job.status = "RUNNING"
                job.started_at = now
                wait = max(0.0, now - job.queued_at)
                self.metrics.queue_wait.labels(job.tenant_group, job.job_type).observe(wait)
                running += 1
            self._update_depth_metrics()

    def _duration_for(self, job_type: str) -> float:
        variation = sum(job_type.encode("utf-8")) % 3
        return self.settings.simulator.job_duration_seconds * (1 + variation * 0.1)

    def _update_depth_metrics(self) -> None:
        running = sum(job.status == "RUNNING" for job in self.jobs.values())
        queued = len(self.queue)
        self.max_running_observed = max(self.max_running_observed, running)
        self.max_queue_observed = max(self.max_queue_observed, queued)
        self.metrics.running.set(running)
        self.metrics.queued.set(queued)
        self.metrics.max_running.set(self.max_running_observed)
        self.metrics.max_queue.set(self.max_queue_observed)


def create_app(settings: Settings | None = None) -> FastAPI:
    selected_settings = settings or load_settings()
    state = SimulatorState(selected_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.simulator_state = state
        scheduler_task = asyncio.create_task(state.scheduler())
        try:
            yield
        finally:
            scheduler_task.cancel()
            await scheduler_task

    application = FastAPI(title="Locust Job Simulator", version="0.1.0", lifespan=lifespan)
    application.state.simulator_state = state

    @application.post("/datasets", status_code=status.HTTP_201_CREATED)
    async def create_dataset(
        request: DatasetRequest,
        x_tenant_id: str = Header(default="tenant-unknown"),
    ) -> dict[str, str]:
        dataset_id = await state.create_dataset(request.name, x_tenant_id)
        return {"datasetId": dataset_id}

    @application.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
    async def create_job(
        request: JobRequest,
        x_tenant_id: str = Header(default="tenant-unknown"),
        x_tenant_group: str = Header(default="balanced"),
    ) -> dict[str, str]:
        if request.tenantId != x_tenant_id:
            raise HTTPException(status_code=400, detail="body and header tenant IDs differ")
        job = await state.submit_job(request, x_tenant_group)
        return {"jobId": job.job_id, "status": job.status}

    @application.get("/jobs/{job_id}")
    async def get_job(job_id: str) -> dict[str, str | float | None]:
        job = await state.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        queue_wait = None
        if job.started_at is not None:
            queue_wait = max(0.0, job.started_at - job.queued_at)
        return {
            "jobId": job.job_id,
            "tenantId": job.tenant_id,
            "datasetId": job.dataset_id,
            "jobType": job.job_type,
            "status": job.status,
            "queueWaitSeconds": queue_wait,
        }

    @application.get("/metrics")
    async def metrics() -> Response:
        return Response(
            content=generate_latest(state.metrics.registry),
            media_type=CONTENT_TYPE_LATEST,
        )

    @application.post("/reset", status_code=status.HTTP_204_NO_CONTENT)
    async def reset() -> Response:
        await state.reset()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return application


app = create_app()
