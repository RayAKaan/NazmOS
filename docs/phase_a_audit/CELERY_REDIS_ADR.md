# ADR: Celery + Redis Clarity

**Status**: ACCEPTED  
**Date**: 2026-08-29  
**Author**: Phase A Audit

---

## 1. Decision

Celery + Redis are **optional, zero-cost toggles** controlled by `USE_CELERY` / `USE_REDIS` settings. When disabled, the app runs fully with FastAPI BackgroundTasks and in-memory caches. The codebase uses **stub patterns** so imports never crash.

---

## 2. Toggle Mechanism

### 2.1 Settings (config.py:26-27)
```python
USE_CELERY: bool = False
USE_REDIS: bool = False
```

### 2.2 Docker Compose Overrides
| Compose File | USE_CELERY | USE_REDIS |
|--------------|------------|-----------|
| `docker-compose.yml` (staging) | `true` | `true` |
| `docker-compose.local.yml` | `false` (omitted) | `false` (omitted) |
| `docker-compose.sqlite.yml` | `false` (auto) | `false` (auto) |
| `docker-compose.prod.yml` | `true` | `true` |

### 2.3 Auto-Detection (config.py:322-325)
```python
if s.DATABASE_URL.startswith("sqlite"):
    object.__setattr__(s, "USE_CELERY", False)
    object.__setattr__(s, "USE_REDIS", False)
```

---

## 3. Celery Architecture

### 3.1 `app/celery_app.py` — Stub or Real
```python
if not settings.USE_CELERY:
    class _StubCeleryApp:
        task = lambda self, *a, **kw: (lambda fn: fn)  # decorator becomes no-op
        def send_task(self, *a, **kw):
            raise RuntimeError("Celery is disabled (USE_CELERY=False)")
    celery_app = _StubCeleryApp()
else:
    from celery import Celery
    celery_app = Celery("NazmOS", broker=settings.REDIS_URL, backend=settings.REDIS_URL, ...)
    # 10 beat schedules, 6 queues, dead-letter handler
```

### 3.2 Task Modules — Conditional Decoration
Every `app/tasks/*.py` uses:
```python
if settings.USE_CELERY:
    from app.celery_app import celery_app
    @celery_app.task(name="...")
    async def my_task(...): ...
```
When `USE_CELERY=False`, tasks are plain async functions — callable directly.

### 3.3 Queues (Staging/Prod)
| Queue | Purpose | Tasks |
|-------|---------|-------|
| `celery` | Default | General |
| `forecasting` | `forecast_tasks.*` | Daily forecast refresh |
| `ingestion` | `ingestion_tasks.*` | File upload, ETL |
| `analytics` | `analytics_tasks.*` | Summary rebuilds |
| `dead_letter` | Failed tasks | Auto-routed on max retries |

### 3.4 Beat Schedule (10 jobs)
- `refresh-all-forecasts`: daily 03:00
- `rebuild-daily-summaries`: daily 01:00
- `cleanup-stale-uploads`: daily 02:00
- `process-pending-deletions`: daily 04:00 (GDPR)
- `process-unprocessed-events`: every 60s (event bus)
- `refresh-model-performance`: daily 05:00
- `daily-full-audit`: daily 06:00
- `goal-progress-snapshot`: daily 07:00
- `learning-reconciliation`: hourly

---

## 4. Redis Architecture

### 4.1 `app/services/cache_service.py` — Singleton with Fallback
```python
async def get_redis(cls):
    if cls._redis is None:
        try:
            cls._redis = aioredis.from_url(settings.REDIS_URL)
            await cls._redis.ping()
        except Exception:
            cls._redis = None  # Graceful degradation
    return cls._redis
```
- **Never crashes** if Redis unavailable — returns `None`
- All cache methods check `if not redis: return None/False`

### 4.2 `app/services/etl_pipeline.py` — Optional Redis
```python
self.redis = None
# Later:
self.redis = aioredis.from_url(settings.REDIS_URL)
```
- ETL pipeline works without Redis (fallback to DB polling)

### 4.3 `llm_rate_limiter.py` — Uses Cache Service
- Rate limiting backed by Redis cache when available
- Falls back to in-memory if Redis unavailable

---

## 5. Zero-Cost Mode (SQLite + No Celery/Redis)

| Component | Zero-Cost Behavior |
|-----------|-------------------|
| `docker-compose.sqlite.yml` | `DATABASE_URL=sqlite+aiosqlite:///./nazmos.db` |
| `config.py` auto-detect | `USE_CELERY=False`, `USE_REDIS=False` |
| `celery_app.py` | Returns `_StubCeleryApp` |
| `cache_service.py` | Returns `None` (in-memory only) |
| Tasks | Decorators become no-ops; functions callable directly |
| Beat | Not running |

---

## 6. Verification Matrix

| Scenario | USE_CELERY | USE_REDIS | Expected Behavior |
|----------|------------|-----------|-------------------|
| Staging (`docker-compose.yml`) | true | true | Full Celery beat + worker, Redis cache |
| Local dev (`docker-compose.local.yml`) | false | false | BackgroundTasks, no cache |
| Zero-cost (`docker-compose.sqlite.yml`) | false (auto) | false (auto) | SQLite, BackgroundTasks |
| Production | true | true | Full stack |

---

## 7. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| `send_task` called when disabled | `_StubCeleryApp.send_task` raises clear `RuntimeError` |
| Redis connection leak | `cache_service` singleton with try/except; no pooling issues |
| Task import side effects | Tasks only decorated inside `if settings.USE_CELERY:` block |
| Beat schedule drift | All times in `Asia/Riyadh` timezone; `enable_utc=True` |

---

## 7. Conclusion

**Celery + Redis are production-grade but fully optional.** The stub pattern ensures the same codebase runs from zero-cost SQLite mode to full staging/production without code changes. No consolidation needed — pattern is clean and documented.