from __future__ import annotations

import time

from perf_framework.config import Settings

_started_at = time.monotonic()


def reset_run_clock() -> None:
    global _started_at
    _started_at = time.monotonic()


def current_phase(settings: Settings) -> str:
    elapsed = time.monotonic() - _started_at
    boundary = 0.0
    for stage in settings.stages:
        boundary += stage.duration
        if elapsed < boundary:
            return stage.name
    return settings.stages[-1].name
