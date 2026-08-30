from datetime import datetime, timezone
from app.celery_app import celery_app

@celery_app.task(name="app.tasks.runtime_smoke_tasks.runtime_smoke_task")
def runtime_smoke_task(nonce: str) -> dict:
    return {"ok": True, "nonce": nonce, "worker_time_utc": datetime.now(timezone.utc).isoformat()}
