from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from uuid import uuid4


class JobPayloadBuilder:
    def __init__(self, template_path: Path) -> None:
        with template_path.open(encoding="utf-8") as handle:
            template = json.load(handle)
        if not isinstance(template, dict):
            raise ValueError("job payload template must contain a JSON object")
        self._template: dict[str, Any] = template

    def build(self, *, tenant_id: str, dataset_id: str, job_type: str) -> dict[str, Any]:
        payload = copy.deepcopy(self._template)
        payload.update(
            {
                "tenantId": tenant_id,
                "datasetId": dataset_id,
                "jobType": job_type,
                "jobName": f"perf-{job_type.lower()}-{uuid4().hex[:10]}",
            }
        )
        return payload
