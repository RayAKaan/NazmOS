from app.celery_app import celery_app
schedule = getattr(celery_app.conf, "beat_schedule", {}) or {}
print(f"BEAT_SCHEDULE_ENTRIES={len(schedule)}")
raise SystemExit(0 if schedule else 1)
