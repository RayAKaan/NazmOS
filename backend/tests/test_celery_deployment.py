"""Tests for Celery deployment durability (Phase 2.1).

Celery is not installed in the test environment, so these tests statically
verify the deployment wiring: the prod worker must consume every queue that
tasks are actually routed to (including the default ``celery`` queue, which
carries tasks without an explicit route such as ``health.ping`` and
``compliance_tasks``), and a celery beat service must exist so scheduled
maintenance jobs run in production.
"""
import re
from pathlib import Path

import yaml

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
CELERY_APP = BACKEND_DIR / "app" / "celery_app.py"
COMPOSE_PROD = REPO_DIR / "docker-compose.prod.yml"


def _declared_queues() -> set[str]:
    """Extract queue names declared in celery_app.py task_queues."""
    text = CELERY_APP.read_text(encoding="utf-8")
    return set(re.findall(r'Queue\("([^"]+)", routing_key=', text))


def _load_compose(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _service_command(compose: dict, service: str) -> str:
    return compose["services"][service]["command"]


def test_prod_worker_consumes_all_declared_queues_except_dlq():
    compose = _load_compose(COMPOSE_PROD)
    declared = _declared_queues()

    assert "celery" in declared, "celery_app must declare a default 'celery' queue"
    command = _service_command(compose, "celery_worker")
    consumed = set(re.findall(r"--queues=([^\s]+)", command)[0].split(","))

    # The default queue must be consumed, otherwise un-routed tasks pile up.
    assert "celery" in consumed
    # Every non-DLQ declared queue must be consumed somewhere.
    assert consumed == (declared - {"dead_letter"}), (
        f"worker consumes {sorted(consumed)} but queues declared are "
        f"{sorted(declared)}"
    )


def test_prod_has_celery_beat_for_scheduled_jobs():
    compose = _load_compose(COMPOSE_PROD)
    assert "celery_beat" in compose["services"], (
        "production needs a celery beat service to run scheduled maintenance "
        "jobs (e.g. process_pending_deletions, cleanup_stale_uploads)"
    )


def test_beat_command_targets_celery_app():
    compose = _load_compose(COMPOSE_PROD)
    command = _service_command(compose, "celery_beat")
    assert "celery -A app.celery_app beat" in command
