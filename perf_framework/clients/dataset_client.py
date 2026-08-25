from __future__ import annotations

from perf_framework.core.base_api_client import BaseAPIClient


class DatasetClient:
    def __init__(self, api: BaseAPIClient) -> None:
        self.api = api

    def create_dataset(self) -> str | None:
        result = self.api.post(
            "/datasets",
            name="POST /datasets",
            json={"name": f"perf-dataset-{self.api.tenant_id}"},
            expected_statuses=(201,),
        )
        dataset_id = result.data.get("datasetId")
        return str(dataset_id) if result.ok and dataset_id else None
