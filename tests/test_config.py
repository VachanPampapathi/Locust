from dataclasses import replace

import pytest

from perf_framework.config import GateSettings, load_settings
from perf_framework.core.gates import evaluate_gate


def test_loads_compute_ci_profile_and_environment_overrides() -> None:
    settings = load_settings(
        "compute",
        environ={
            "CI_MODE": "true",
            "TENANT_COUNT": "42",
            "SIM_COMPUTE_UNITS": "300",
            "MAX_P95_MS": "250",
        },
    )

    assert settings.ci_mode is True
    assert settings.tenant_count == 42
    assert len(settings.stages) == 6
    assert settings.stages[0].duration == 2
    assert settings.simulator.physical_capacity == 30
    assert settings.gate.max_p95_ms == 250


def test_unknown_scenario_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown scenario"):
        load_settings("missing", environ={})


def test_gate_checks_failure_ratio_and_p95() -> None:
    gate = GateSettings(enabled=True, max_failure_ratio=0.01, max_p95_ms=500)
    assert evaluate_gate(failure_ratio=0.0, p95_ms=100, gate=gate) == []
    failures = evaluate_gate(failure_ratio=0.02, p95_ms=600, gate=gate)
    assert len(failures) == 2
    assert evaluate_gate(
        failure_ratio=1.0,
        p95_ms=10_000,
        gate=replace(gate, enabled=False),
    ) == []
