from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from perf_framework.config import Settings
from perf_framework.core.context import current_phase


@dataclass(frozen=True)
class APIResult:
    ok: bool
    status_code: int
    data: dict[str, Any]


class BaseAPIClient:
    """Locust-aware HTTP adapter shared by all domain clients."""

    def __init__(
        self,
        http_client: Any,
        settings: Settings,
        tenant_id: str,
        tenant_group: str,
    ) -> None:
        self.http_client = http_client
        self.settings = settings
        self.tenant_id = tenant_id
        self.tenant_group = tenant_group

    def get(
        self,
        path: str,
        *,
        name: str,
        expected_statuses: Iterable[int] = (200,),
    ) -> APIResult:
        return self.request("GET", path, name=name, expected_statuses=expected_statuses)

    def post(
        self,
        path: str,
        *,
        name: str,
        json: Mapping[str, Any],
        expected_statuses: Iterable[int] = (200, 201, 202),
    ) -> APIResult:
        return self.request(
            "POST",
            path,
            name=name,
            json=dict(json),
            expected_statuses=expected_statuses,
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        name: str,
        expected_statuses: Iterable[int],
        json: Mapping[str, Any] | None = None,
    ) -> APIResult:
        expected = set(expected_statuses)
        correlation_id = str(uuid4())
        headers = {
            "X-Tenant-ID": self.tenant_id,
            "X-Tenant-Group": self.tenant_group,
            "X-Correlation-ID": correlation_id,
            "X-Test-Phase": current_phase(self.settings),
        }
        context = {
            "tenant_group": self.tenant_group,
            "phase": current_phase(self.settings),
            "correlation_id": correlation_id,
        }
        with self.http_client.request(
            method,
            path,
            name=name,
            headers=headers,
            json=json,
            context=context,
            catch_response=True,
        ) as response:
            if response.status_code not in expected:
                response.failure(
                    f"unexpected status {response.status_code}; expected {sorted(expected)}"
                )
                return APIResult(False, response.status_code, _safe_json(response))
            data = _safe_json(response)
            if not isinstance(data, dict):
                response.failure("response body must be a JSON object")
                return APIResult(False, response.status_code, {})
            response.success()
            return APIResult(True, response.status_code, data)


def _safe_json(response: Any) -> dict[str, Any]:
    try:
        data = response.json()
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}
