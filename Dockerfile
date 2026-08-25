FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY perf_framework ./perf_framework
COPY simulator ./simulator
COPY config ./config
COPY locustfile.py ./

RUN pip install --no-cache-dir .

EXPOSE 8000
