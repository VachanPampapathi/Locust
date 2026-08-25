from __future__ import annotations

from locust import LoadTestShape

from perf_framework.config import load_settings
from perf_framework.users import HeavyUser, NormalUser

USER_CLASSES = {
    "NormalUser": NormalUser,
    "HeavyUser": HeavyUser,
}


class StepLoadShape(LoadTestShape):
    settings = load_settings()

    def tick(self):  # type: ignore[no-untyped-def]
        elapsed = self.get_run_time()
        boundary = 0.0
        for stage in self.settings.stages:
            boundary += stage.duration
            if elapsed < boundary:
                classes = [USER_CLASSES[name] for name in stage.user_classes]
                return stage.users, stage.spawn_rate, classes
        return None
