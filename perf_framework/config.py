from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Stage:
    name: str
    duration: float
    users: int
    spawn_rate: float
    user_classes: tuple[str, ...]


@dataclass(frozen=True)
class SimulatorSettings:
    compute_units: int
    units_per_job: int
    mixed_job_limit: int
    job_duration_seconds: float
    scheduler_interval_seconds: float

    @property
    def physical_capacity(self) -> int:
        return self.compute_units // self.units_per_job


@dataclass(frozen=True)
class GateSettings:
    enabled: bool
    max_failure_ratio: float
    max_p95_ms: float


@dataclass(frozen=True)
class Settings:
    scenario: str
    target_host: str
    tenant_count: int
    poll_interval_seconds: float
    poll_timeout_seconds: float
    artifact_dir: Path
    normal_wait_min_seconds: float
    normal_wait_max_seconds: float
    heavy_wait_min_seconds: float
    heavy_wait_max_seconds: float
    job_types: tuple[str, ...]
    stages: tuple[Stage, ...]
    simulator: SimulatorSettings
    gate: GateSettings
    ci_mode: bool

    def public_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["artifact_dir"] = str(self.artifact_dir)
        result["simulator"]["physical_capacity"] = self.simulator.physical_capacity
        return result


def _deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _deep_merge(dict(result[key]), value)
        else:
            result[key] = value
    return result


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Configuration must be a mapping: {path}")
    return loaded


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings(
    scenario: str | None = None,
    *,
    config_dir: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Settings:
    env = dict(os.environ if environ is None else environ)
    selected = scenario or env.get("SCENARIO", "compute")
    root = config_dir or PROJECT_ROOT / "config"
    base = _load_yaml(root / "base.yaml")
    profile_path = root / "scenarios" / f"{selected}.yaml"
    if not profile_path.exists():
        available = ", ".join(path.stem for path in sorted((root / "scenarios").glob("*.yaml")))
        raise ValueError(f"Unknown scenario {selected!r}. Available scenarios: {available}")
    data = _deep_merge(base, _load_yaml(profile_path))

    ci_mode = _as_bool(env.get("CI_MODE", "false"))
    stage_key = "ci_stages" if ci_mode else "stages"
    raw_stages = data.get(stage_key) or data.get("stages", [])

    overrides: dict[str, tuple[str, Any]] = {
        "TARGET_HOST": ("target_host", str),
        "TENANT_COUNT": ("tenant_count", int),
        "POLL_INTERVAL_SECONDS": ("poll_interval_seconds", float),
        "POLL_TIMEOUT_SECONDS": ("poll_timeout_seconds", float),
        "ARTIFACT_DIR": ("artifact_dir", str),
    }
    for env_name, (key, cast) in overrides.items():
        if env_name in env:
            data[key] = cast(env[env_name])

    simulator = dict(data["simulator"])
    simulator_overrides: dict[str, tuple[str, Any]] = {
        "SIM_COMPUTE_UNITS": ("compute_units", int),
        "SIM_UNITS_PER_JOB": ("units_per_job", int),
        "SIM_MIXED_JOB_LIMIT": ("mixed_job_limit", int),
        "SIM_JOB_DURATION_SECONDS": ("job_duration_seconds", float),
    }
    for env_name, (key, cast) in simulator_overrides.items():
        if env_name in env:
            simulator[key] = cast(env[env_name])

    gate = dict(data["gate"])
    if "GATE_ENABLED" in env:
        gate["enabled"] = _as_bool(env["GATE_ENABLED"])
    if "MAX_FAILURE_RATIO" in env:
        gate["max_failure_ratio"] = float(env["MAX_FAILURE_RATIO"])
    if "MAX_P95_MS" in env:
        gate["max_p95_ms"] = float(env["MAX_P95_MS"])

    settings = Settings(
        scenario=selected,
        target_host=str(data["target_host"]).rstrip("/"),
        tenant_count=int(data["tenant_count"]),
        poll_interval_seconds=float(data["poll_interval_seconds"]),
        poll_timeout_seconds=float(data["poll_timeout_seconds"]),
        artifact_dir=Path(data["artifact_dir"]),
        normal_wait_min_seconds=float(data["normal_wait_seconds"][0]),
        normal_wait_max_seconds=float(data["normal_wait_seconds"][1]),
        heavy_wait_min_seconds=float(data["heavy_wait_seconds"][0]),
        heavy_wait_max_seconds=float(data["heavy_wait_seconds"][1]),
        job_types=tuple(str(item) for item in data["job_types"]),
        stages=tuple(
            Stage(
                name=str(stage["name"]),
                duration=float(stage["duration"]),
                users=int(stage["users"]),
                spawn_rate=float(stage["spawn_rate"]),
                user_classes=tuple(stage.get("user_classes", ["NormalUser"])),
            )
            for stage in raw_stages
        ),
        simulator=SimulatorSettings(
            compute_units=int(simulator["compute_units"]),
            units_per_job=int(simulator["units_per_job"]),
            mixed_job_limit=int(simulator["mixed_job_limit"]),
            job_duration_seconds=float(simulator["job_duration_seconds"]),
            scheduler_interval_seconds=float(simulator["scheduler_interval_seconds"]),
        ),
        gate=GateSettings(
            enabled=bool(gate["enabled"]),
            max_failure_ratio=float(gate["max_failure_ratio"]),
            max_p95_ms=float(gate["max_p95_ms"]),
        ),
        ci_mode=ci_mode,
    )
    _validate(settings)
    return settings


def _validate(settings: Settings) -> None:
    if settings.tenant_count < 2:
        raise ValueError("tenant_count must be at least 2")
    if settings.simulator.compute_units <= 0 or settings.simulator.units_per_job <= 0:
        raise ValueError("simulator compute settings must be positive")
    if settings.simulator.physical_capacity < 1:
        raise ValueError("simulator physical capacity must be at least 1")
    if settings.simulator.mixed_job_limit < 1:
        raise ValueError("mixed_job_limit must be at least 1")
    if not settings.job_types:
        raise ValueError("at least one job type is required")
    if not settings.stages:
        raise ValueError("at least one load stage is required")
    invalid_stage = any(
        stage.duration <= 0 or stage.users < 0 or stage.spawn_rate <= 0
        for stage in settings.stages
    )
    if invalid_stage:
        raise ValueError("stage duration/spawn_rate must be positive and users cannot be negative")
