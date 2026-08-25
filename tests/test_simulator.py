import asyncio
from dataclasses import replace

import httpx

from perf_framework.config import load_settings
from simulator.app import create_app


async def _create_dataset(client: httpx.AsyncClient, tenant: str = "tenant-001") -> str:
    response = await client.post(
        "/datasets",
        json={"name": "dataset"},
        headers={"X-Tenant-ID": tenant},
    )
    assert response.status_code == 201
    return response.json()["datasetId"]


async def _submit_job(
    client: httpx.AsyncClient,
    dataset_id: str,
    index: int,
    job_type: str = "EXPORT",
) -> str:
    response = await client.post(
        "/jobs",
        json={
            "tenantId": "tenant-001",
            "datasetId": dataset_id,
            "jobType": job_type,
            "jobName": f"job-{index}",
        },
        headers={"X-Tenant-ID": "tenant-001", "X-Tenant-Group": "control"},
    )
    assert response.status_code == 202
    return response.json()["jobId"]


async def test_compute_capacity_queues_above_physical_limit() -> None:
    settings = load_settings("compute", environ={})
    simulator = replace(
        settings.simulator,
        job_duration_seconds=0.08,
        scheduler_interval_seconds=0.002,
    )
    app = create_app(replace(settings, simulator=simulator))

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            dataset_id = await _create_dataset(client)
            job_ids = [await _submit_job(client, dataset_id, index) for index in range(30)]
            await asyncio.sleep(0.02)
            state = app.state.simulator_state
            assert state.max_running_observed == 25
            assert state.max_queue_observed >= 5

            await asyncio.sleep(0.25)
            statuses = [
                (await client.get(f"/jobs/{job_id}")).json()["status"]
                for job_id in job_ids
            ]
            assert set(statuses) == {"COMPLETED"}

            metrics = (await client.get("/metrics")).text
            assert "simulator_max_running_jobs 25.0" in metrics
            assert "simulator_job_queue_wait_seconds" in metrics

            reset = await client.post("/reset")
            assert reset.status_code == 204
            assert state.jobs == {}


async def test_mixed_job_limit_is_independent_of_compute_capacity() -> None:
    settings = load_settings("mixed", environ={})
    simulator = replace(
        settings.simulator,
        job_duration_seconds=0.2,
        scheduler_interval_seconds=0.002,
    )
    app = create_app(replace(settings, simulator=simulator))

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            dataset_id = await _create_dataset(client)
            job_types = settings.job_types
            for index in range(55):
                await _submit_job(client, dataset_id, index, job_types[index % len(job_types)])
            await asyncio.sleep(0.02)

            state = app.state.simulator_state
            assert settings.simulator.physical_capacity == 60
            assert state.max_running_observed == 50
            assert state.max_queue_observed >= 5
