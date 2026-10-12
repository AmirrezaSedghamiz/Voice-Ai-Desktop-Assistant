# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Prevent Python bytecode generation and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install lightweight system utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Layer Cache: Copy requirements FIRST so dependencies are cached across code changes
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy source code and project configuration
COPY src/ ./src/
COPY tests/ ./tests/
COPY scripts/ ./scripts/

# Ensure host-mounted models and logs directories exist
RUN mkdir -p /app/models /app/logs /app/config

# Volumes: models and data are MOUNTED from host, never baked into image layers
VOLUME ["/app/models", "/app/logs"]

# Loopback / internal port
EXPOSE 8080

CMD ["python", "-m", "src.cli"]
