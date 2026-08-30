from app.celery_app import celery_app
stats = celery_app.control.inspect(timeout=2).stats() or {}
print(f"CELERY_WORKERS={len(stats)}")
raise SystemExit(0 if stats else 1)
