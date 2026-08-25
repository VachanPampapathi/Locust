from __future__ import annotations

import json
import threading
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

from locust import events
from locust.runners import WorkerRunner
from prometheus_client.parser import text_string_to_metric_families

from perf_framework.config import Settings
from perf_framework.core.context import reset_run_clock
from perf_framework.core.gates import evaluate_gate, percentile

_samples: dict[tuple[str, str], list[float]] = defaultdict(list)
_sample_lock = threading.Lock()
_registered = False


def register_metrics_hooks(settings: Settings) -> None:
    global _registered
    if _registered:
        return
    _registered = True

    @events.test_start.add_listener
    def on_test_start(environment: Any, **_: Any) -> None:
        reset_run_clock()
        with _sample_lock:
            _samples.clear()

    @events.request.add_listener
    def on_request(
        request_type: str,
        name: str,
        response_time: float,
        response_length: int,
        exception: Exception | None,
        context: dict[str, Any] | None = None,
        **_: Any,
    ) -> None:
        del request_type, name, response_length, exception
        details = context or {}
        group = str(details.get("tenant_group", "unknown"))
        phase = str(details.get("phase", "unknown"))
        with _sample_lock:
            _samples[(group, phase)].append(float(response_time))

    @events.test_stop.add_listener
    def on_test_stop(environment: Any, **_: Any) -> None:
        if isinstance(environment.runner, WorkerRunner):
            return
        summary = build_summary(environment, settings)
        output = settings.artifact_dir / "summary.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        if summary["gate"]["failures"]:
            environment.process_exit_code = 1


def build_summary(environment: Any, settings: Settings) -> dict[str, Any]:
    total = environment.stats.total
    request_count = int(total.num_requests)
    failure_count = int(total.num_failures)
    failure_ratio = failure_count / request_count if request_count else 0.0
    p95_ms = float(total.get_response_time_percentile(0.95) or 0.0)
    gate_failures = evaluate_gate(
        failure_ratio=failure_ratio,
        p95_ms=p95_ms,
        gate=settings.gate,
    )
    with _sample_lock:
        tenant_phases = {
            f"{group}:{phase}": {
                "samples": len(values),
                "p95_ms": percentile(values, 0.95),
            }
            for (group, phase), values in sorted(_samples.items())
        }
    return {
        "disclaimer": (
            "Simulator measurements demonstrate framework behavior and are not Cloudwick "
            "capacity findings or production SLAs."
        ),
        "configuration": settings.public_dict(),
        "locust": {
            "requests": request_count,
            "failures": failure_count,
            "failure_ratio": failure_ratio,
            "p95_ms": p95_ms,
            "requests_per_second": float(total.total_rps or 0.0),
        },
        "tenant_phases": tenant_phases,
        "simulator": _fetch_simulator_metrics(settings.target_host),
        "gate": {
            "enabled": settings.gate.enabled,
            "passed": not gate_failures,
            "failures": gate_failures,
        },
    }


def _fetch_simulator_metrics(target_host: str) -> dict[str, float | str]:
    wanted = {
        "simulator_max_running_jobs",
        "simulator_max_queue_depth",
        "simulator_running_jobs",
        "simulator_queue_depth",
    }
    try:
        with urllib.request.urlopen(f"{target_host}/metrics", timeout=2) as response:  # noqa: S310
            body = response.read().decode("utf-8")
        result: dict[str, float | str] = {}
        for family in text_string_to_metric_families(body):
            for sample in family.samples:
                if sample.name in wanted:
                    result[sample.name] = float(sample.value)
        return result
    except (OSError, ValueError) as exc:
        return {"error": str(exc)}


def write_summary_for_test(summary: dict[str, Any], path: Path) -> None:
    """Small testable writer used by integration tooling."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
