# NazmOS Runtime Readiness

Required real stack: PostgreSQL 17, Redis 7, Celery worker, Celery Beat, FastAPI, Next.js. SQLite, in-memory Redis, synchronous background execution, and direct API-only validation do not satisfy readiness.

```bash
cp .env.runtime-test.example .env.runtime-test
docker compose --env-file .env.runtime-test -f docker-compose.local.yml up --build -d
make runtime-readiness
```

The compose stack gates API/workers/beat on migration success and uses real health checks. Runtime readiness is separate from the full V5 experiment.
