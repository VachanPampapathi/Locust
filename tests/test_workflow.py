from dataclasses import replace

import pytest

from perf_framework.config import load_settings
from perf_framework.workflows.job_workflow import JobWorkflow, WorkflowError


class DatasetStub:
    def create_dataset(self) -> str:
        return "dataset-1"


class JobStub:
    def create_job(self, payload):  # type: ignore[no-untyped-def]
        return "job-1"

    def get_job(self, job_id):  # type: ignore[no-untyped-def]
        return {"jobId": job_id, "status": "QUEUED"}


class BuilderStub:
    def build(self, **kwargs):  # type: ignore[no-untyped-def]
        return kwargs


def test_workflow_enforces_polling_deadline() -> None:
    settings = load_settings("compute", environ={})
    settings = replace(settings, poll_interval_seconds=0.001, poll_timeout_seconds=0.005)
    workflow = JobWorkflow(
        settings,
        DatasetStub(),  # type: ignore[arg-type]
        JobStub(),  # type: ignore[arg-type]
        BuilderStub(),  # type: ignore[arg-type]
        "tenant-001",
    )

    with pytest.raises(WorkflowError, match="polling deadline"):
        workflow.execute("EXPORT")
