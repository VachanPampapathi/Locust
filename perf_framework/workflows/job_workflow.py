from __future__ import annotations

import time

import gevent

from perf_framework.builders.payload_builder import JobPayloadBuilder
from perf_framework.clients.dataset_client import DatasetClient
from perf_framework.clients.job_client import JobClient
from perf_framework.config import Settings


class WorkflowError(RuntimeError):
    pass


class JobWorkflow:
    def __init__(
        self,
        settings: Settings,
        dataset_client: DatasetClient,
        job_client: JobClient,
        payload_builder: JobPayloadBuilder,
        tenant_id: str,
    ) -> None:
        self.settings = settings
        self.dataset_client = dataset_client
        self.job_client = job_client
        self.payload_builder = payload_builder
        self.tenant_id = tenant_id

    def execute(self, job_type: str) -> dict[str, object]:
        dataset_id = self.dataset_client.create_dataset()
        if not dataset_id:
            raise WorkflowError("dataset creation failed")
        payload = self.payload_builder.build(
            tenant_id=self.tenant_id,
            dataset_id=dataset_id,
            job_type=job_type,
        )
        job_id = self.job_client.create_job(payload)
        if not job_id:
            raise WorkflowError("job submission failed")

        deadline = time.monotonic() + self.settings.poll_timeout_seconds
        while time.monotonic() < deadline:
            job = self.job_client.get_job(job_id)
            if job is None:
                raise WorkflowError(f"job lookup failed for {job_id}")
            if job.get("status") == "COMPLETED":
                return job
            if job.get("status") == "FAILED":
                raise WorkflowError(f"job {job_id} failed")
            gevent.sleep(self.settings.poll_interval_seconds)
        raise WorkflowError(f"job {job_id} did not complete before polling deadline")
