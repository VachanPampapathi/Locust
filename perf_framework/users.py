from __future__ import annotations

import itertools
import random
import time
from pathlib import Path
from typing import ClassVar

from locust import HttpUser, task

from perf_framework.builders.payload_builder import JobPayloadBuilder
from perf_framework.clients.dataset_client import DatasetClient
from perf_framework.clients.job_client import JobClient
from perf_framework.config import PROJECT_ROOT, Settings, load_settings
from perf_framework.core.base_api_client import BaseAPIClient
from perf_framework.core.context import current_phase
from perf_framework.core.tenant_allocator import TenantAllocator
from perf_framework.workflows.job_workflow import JobWorkflow, WorkflowError

SETTINGS = load_settings()
ALLOCATOR = TenantAllocator(SETTINGS.tenant_count, noisy_neighbor=SETTINGS.scenario == "noisy")
PAYLOAD_BUILDER = JobPayloadBuilder(PROJECT_ROOT / "perf_framework" / "data" / "create_job.json")


class FrameworkUser(HttpUser):
    abstract = True
    settings: ClassVar[Settings] = SETTINGS
    tenant_group = "balanced"
    heavy = False

    def on_start(self) -> None:
        tenant_id = ALLOCATOR.allocate_heavy() if self.heavy else ALLOCATOR.allocate_normal()
        if self.settings.scenario == "noisy":
            self.tenant_group = "noisy" if self.heavy else "control"
        api = BaseAPIClient(self.client, self.settings, tenant_id, self.tenant_group)
        self.workflow = JobWorkflow(
            self.settings,
            DatasetClient(api),
            JobClient(api),
            PAYLOAD_BUILDER,
            tenant_id,
        )
        self.job_types = itertools.cycle(self.settings.job_types)

    def wait_time(self) -> float:
        if self.heavy:
            return random.uniform(
                self.settings.heavy_wait_min_seconds,
                self.settings.heavy_wait_max_seconds,
            )
        return random.uniform(
            self.settings.normal_wait_min_seconds,
            self.settings.normal_wait_max_seconds,
        )

    def run_workflow(self) -> None:
        started = time.perf_counter()
        try:
            self.workflow.execute(next(self.job_types))
        except WorkflowError as exc:
            self.environment.events.request.fire(
                request_type="WORKFLOW",
                name="Job workflow",
                response_time=(time.perf_counter() - started) * 1000,
                response_length=0,
                exception=exc,
                context={
                    "tenant_group": self.tenant_group,
                    "phase": current_phase(self.settings),
                },
            )


class NormalUser(FrameworkUser):
    weight = 1

    @task
    def submit_and_wait_for_job(self) -> None:
        self.run_workflow()


class HeavyUser(FrameworkUser):
    weight = 1
    heavy = True

    @task
    def submit_jobs_aggressively(self) -> None:
        self.run_workflow()


def payload_template_path() -> Path:
    return PROJECT_ROOT / "perf_framework" / "data" / "create_job.json"
