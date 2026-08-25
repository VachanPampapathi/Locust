from __future__ import annotations

import threading


class TenantAllocator:
    """Process-local round-robin allocator with an explicit noisy tenant."""

    def __init__(self, tenant_count: int, *, noisy_neighbor: bool = False) -> None:
        if tenant_count < 2:
            raise ValueError("tenant_count must be at least 2")
        self.tenant_count = tenant_count
        self.noisy_neighbor = noisy_neighbor
        self._next_index = 2 if noisy_neighbor else 1
        self._lock = threading.Lock()

    @staticmethod
    def _tenant_id(index: int) -> str:
        return f"tenant-{index:03d}"

    def allocate_normal(self) -> str:
        lower = 2 if self.noisy_neighbor else 1
        with self._lock:
            allocated = self._next_index
            self._next_index += 1
            if self._next_index > self.tenant_count:
                self._next_index = lower
        return self._tenant_id(allocated)

    def allocate_heavy(self) -> str:
        return self._tenant_id(1)
