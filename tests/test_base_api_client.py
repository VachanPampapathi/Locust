from typing import Any

from perf_framework.config import load_settings
from perf_framework.core.base_api_client import BaseAPIClient


class FakeResponse:
    def __init__(self, status_code: int, data: dict[str, Any]) -> None:
        self.status_code = status_code
        self.data = data
        self.failure_message: str | None = None
        self.succeeded = False

    def __enter__(self):
        return self

    def __exit__(self, *_: Any) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.data

    def failure(self, message: str) -> None:
        self.failure_message = message

    def success(self) -> None:
        self.succeeded = True


class FakeHttpClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.call: dict[str, Any] = {}

    def request(self, method: str, path: str, **kwargs: Any) -> FakeResponse:
        self.call = {"method": method, "path": path, **kwargs}
        return self.response


def test_base_client_adds_context_headers_and_stable_name() -> None:
    response = FakeResponse(201, {"datasetId": "dataset-1"})
    http = FakeHttpClient(response)
    client = BaseAPIClient(http, load_settings("compute", environ={}), "tenant-007", "control")

    result = client.post(
        "/datasets",
        name="POST /datasets",
        json={"name": "demo"},
        expected_statuses=(201,),
    )

    assert result.ok is True
    assert response.succeeded is True
    assert http.call["name"] == "POST /datasets"
    assert http.call["headers"]["X-Tenant-ID"] == "tenant-007"
    assert http.call["context"]["tenant_group"] == "control"
    assert "tenant-007" not in http.call["name"]


def test_base_client_marks_unexpected_status_as_failure() -> None:
    response = FakeResponse(500, {"detail": "boom"})
    client = BaseAPIClient(
        FakeHttpClient(response),
        load_settings("compute", environ={}),
        "tenant-001",
        "balanced",
    )

    result = client.get("/jobs/job-1", name="GET /jobs/{id}")

    assert result.ok is False
    assert "unexpected status 500" in (response.failure_message or "")
