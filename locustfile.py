from perf_framework.config import load_settings
from perf_framework.core.metrics import register_metrics_hooks
from perf_framework.load_shape import StepLoadShape
from perf_framework.users import HeavyUser, NormalUser

SETTINGS = load_settings()
register_metrics_hooks(SETTINGS)

__all__ = ["HeavyUser", "NormalUser", "StepLoadShape"]
