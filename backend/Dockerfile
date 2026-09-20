# Production Dockerfile for NazmOS backend.
FROM python:3.12-slim AS base

WORKDIR /app

# Install system dependencies required by pandas, statsforecast, and python-magic.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

RUN chmod +x /app/scripts/runtime_worker_health.py /app/scripts/runtime_beat_health.py

# `production` is the stage target referenced by docker-compose.prod.yml and
# the deploy pipeline (`--target production`). It inherits the base runtime;
# the stage exists so the production image is an explicit, peer-reviewed target
# rather than an implicitly-selected default.
FROM base AS production
