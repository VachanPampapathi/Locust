from __future__ import annotations

from perf_framework.config import GateSettings


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * quantile)))
    return float(ordered[index])


def evaluate_gate(
    *,
    failure_ratio: float,
    p95_ms: float,
    gate: GateSettings,
) -> list[str]:
    if not gate.enabled:
        return []
    failures: list[str] = []
    if failure_ratio > gate.max_failure_ratio:
        failures.append(
            f"failure ratio {failure_ratio:.4f} exceeded {gate.max_failure_ratio:.4f}"
        )
    if p95_ms > gate.max_p95_ms:
        failures.append(f"P95 {p95_ms:.1f} ms exceeded {gate.max_p95_ms:.1f} ms")
    return failures
