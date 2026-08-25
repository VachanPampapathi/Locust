from collections import Counter

from perf_framework.core.tenant_allocator import TenantAllocator


def test_balanced_allocator_cycles_evenly() -> None:
    allocator = TenantAllocator(4)
    allocations = [allocator.allocate_normal() for _ in range(8)]

    assert allocations[:4] == ["tenant-001", "tenant-002", "tenant-003", "tenant-004"]
    assert set(Counter(allocations).values()) == {2}


def test_noisy_neighbor_is_reserved_for_heavy_user() -> None:
    allocator = TenantAllocator(4, noisy_neighbor=True)
    normal = [allocator.allocate_normal() for _ in range(6)]

    assert allocator.allocate_heavy() == "tenant-001"
    assert "tenant-001" not in normal
    assert normal == [
        "tenant-002",
        "tenant-003",
        "tenant-004",
        "tenant-002",
        "tenant-003",
        "tenant-004",
    ]
