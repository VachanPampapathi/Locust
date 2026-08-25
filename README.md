# Locust Performance & Scale Framework — Reduced Prototype

This repository is a runnable companion to the broader [Eraser architecture](https://app.eraser.io/workspace/Jv0VJeXqSPCJtBmWst7H). The architecture describes a mature multi-tenant performance framework; this code intentionally proves only its most important seams with a deterministic local simulator.

> Results from the simulator demonstrate test-framework behavior. They are not Cloudwick capacity findings and the configured thresholds are not production SLAs.

## What is implemented

```text
Locust user
  -> JobWorkflow
     -> DatasetClient / JobClient
        -> BaseAPIClient
           -> FastAPI simulator
```

- YAML configuration with environment overrides.
- Stable Locust request naming, correlation headers, and tenant-group context.
- Deterministic allocation across 100 tenants.
- External job payload template loaded once per Locust process.
- Normal and heavy personas plus a reusable step load shape.
- An asynchronous FIFO job simulator with Prometheus metrics.
- Compute saturation, mixed-job boundary, and noisy-neighbor profiles.
- JSON/HTML/CSV reports, a simple P95/failure-rate gate, Docker Compose, and one CI workflow.

The simulator does **not** implement authentication, persistent storage, the shared 900/800 slot pool, the 1,000 same-type quota, fault injection, results download, Grafana, or real cloud telemetry.

## Quick start with Docker

Run the default compute-saturation profile:

```bash
SCENARIO=compute docker compose up --build --abort-on-container-exit --exit-code-from locust
```

Other demos:

```bash
SCENARIO=mixed docker compose up --build --abort-on-container-exit --exit-code-from locust
SCENARIO=noisy docker compose up --build --abort-on-container-exit --exit-code-from locust
```

Use `CI_MODE=true` for the time-compressed stages:

```bash
SCENARIO=compute CI_MODE=true docker compose up --build --abort-on-container-exit --exit-code-from locust
```

Reports are written to `artifacts/`. Stop and remove the containers after a run with `docker compose down`.

## Run directly with Python

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

In terminal one:

```bash
SCENARIO=compute uvicorn simulator.app:app --port 8000
```

In terminal two:

```bash
SCENARIO=compute locust -f locustfile.py --headless --host http://127.0.0.1:8000 \
  --html artifacts/report.html --csv artifacts/stats
```

Locust remains compatible with its standard `--master` and `--worker` flags. The reduced demo defaults to a single headless process so it is easy to present and run in CI.

## Scenario interpretation

### Compute saturation

`compute` uses one job type and the assignment defaults of 254 compute units and 10 units per job. At most 25 jobs can be `RUNNING`; increased Locust users should grow the queue rather than the running count.

### Mixed-job boundary

`mixed` raises compute capacity to 60 jobs and submits five job types. The separate mixed-job limit caps running work at 50, allowing the logical boundary to be observed without the physical 25-job limit masking it.

### Noisy neighbor

`noisy` uses three phases: balanced control traffic, a burst that introduces `HeavyUser` on `tenant-001`, and recovery. Normal users use tenants 002–100. FIFO scheduling intentionally makes the control-tenant impact visible in the per-phase summary.

## Configuration

Common defaults live in `config/base.yaml`; scenario-specific stages and simulator overrides live under `config/scenarios/`.

Supported environment overrides include:

- `SCENARIO=compute|mixed|noisy`
- `CI_MODE=true|false`
- `TARGET_HOST`, `TENANT_COUNT`, `POLL_INTERVAL_SECONDS`, `POLL_TIMEOUT_SECONDS`
- `ARTIFACT_DIR`, `GATE_ENABLED`, `MAX_FAILURE_RATIO`, `MAX_P95_MS`
- `SIM_COMPUTE_UNITS`, `SIM_UNITS_PER_JOB`, `SIM_MIXED_JOB_LIMIT`
- `SIM_JOB_DURATION_SECONDS`

The simulator exposes `POST /datasets`, `POST /jobs`, `GET /jobs/{id}`, `GET /metrics`, and `POST /reset`.

## Replacing the simulator

To target a real product, retain the framework core, users, load shape, reporting, and workflow boundaries. Replace the dataset/job client paths and response-field mappings, add the real authentication strategy, and point `TARGET_HOST` at a dedicated performance environment. Product-specific SLA values and backend monitoring must be supplied before treating a run as a release gate.

## Development checks

```bash
ruff check .
pytest
```

GitHub Actions runs both checks and a shortened headless compute scenario, then uploads the generated reports.
