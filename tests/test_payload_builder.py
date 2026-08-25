import json

from perf_framework.builders.payload_builder import JobPayloadBuilder


def test_payload_template_is_deep_copied(tmp_path) -> None:
    template = tmp_path / "job.json"
    template.write_text(
        json.dumps({"options": {"priority": "NORMAL"}, "tenantId": ""}),
        encoding="utf-8",
    )
    builder = JobPayloadBuilder(template)

    first = builder.build(tenant_id="tenant-001", dataset_id="d-1", job_type="EXPORT")
    first["options"]["priority"] = "CHANGED"
    second = builder.build(tenant_id="tenant-002", dataset_id="d-2", job_type="IMPORT")

    assert second["options"]["priority"] == "NORMAL"
    assert second["tenantId"] == "tenant-002"
    assert second["datasetId"] == "d-2"
