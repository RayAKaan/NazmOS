# Production Dockerfile for NazmOS backend.
#
# Multi-stage build:
#   builder    - installs all build/runtime dependencies and the application.
#   production - copies only installed packages + application code (no tests/dev artifacts).
#
# The "production" stage is the target referenced by docker-compose.prod.yml.

FROM python:3.12-slim AS builder

WORKDIR /app

# Install system dependencies required by pandas, prophet, and python-magic.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .


FROM python:3.12-slim AS production

ENV PYTHONUNBUFFERED=1

# Runtime-only system dependencies. postgresql-client is required by the
# automated backup/restore-drill tooling (scripts/backup_postgres.py).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages and the application code from the builder stage.
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

WORKDIR /app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
