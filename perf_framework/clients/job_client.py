from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from perf_framework.core.base_api_client import BaseAPIClient


class JobClient:
    def __init__(self, api: BaseAPIClient) -> None:
        self.api = api

    def create_job(self, payload: Mapping[str, Any]) -> str | None:
        result = self.api.post(
            "/jobs",
            name="POST /jobs",
            json=payload,
            expected_statuses=(202,),
        )
        job_id = result.data.get("jobId")
        return str(job_id) if result.ok and job_id else None

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        result = self.api.get(
            f"/jobs/{job_id}",
            name="GET /jobs/{id}",
            expected_statuses=(200,),
        )
        return result.data if result.ok else None
