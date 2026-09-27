"""Phase 2A deployment invariants — Temporal is the single execution substrate.

Static wiring checks (no broker/worker containers are required to run them):

- No Celery service, ``USE_CELERY`` config, or ``app.celery_app`` module may
  remain anywhere in the deployment surface (compose files, backend app code,
  CI).
- The API/backend and the nazmos-worker containers must run against the real
  Temporal server with ``USE_TEMPORAL=true`` (no silent local fallback), and
  the worker's command must be the Temporal worker entry point.
- Every registered workflow is a defn-decorated Temporal workflow and every
  default Temporal Schedule maps to a known workflow.
"""
from pathlib import Path

import yaml

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent

COMPOSE_FILES = [
    "docker-compose.yml",
    "docker-compose.prod.yml",
    "docker-compose.local.yml",
    "docker-compose.sqlite.yml",
]
SUBSTRATE_COMPOSE = [  # stacks that must run the real Temporal substrate
    "docker-compose.yml",
    "docker-compose.prod.yml",
    "docker-compose.local.yml",
]


def _compose(name: str) -> dict:
    return yaml.safe_load((REPO_DIR / name).read_text(encoding="utf-8"))


def test_no_celery_services_or_config_in_any_compose():
    for name in COMPOSE_FILES:
        raw = (REPO_DIR / name).read_text(encoding="utf-8")
        assert "USE_CELERY" not in raw, f"{name} still sets USE_CELERY"
        assert "app.celery_app" not in raw, f"{name} still references app.celery_app"
        services = _compose(name).get("services", {})
        assert "celery_worker" not in services, f"{name} still defines celery_worker"
        assert "celery_beat" not in services, f"{name} still defines celery_beat"


def test_celery_surface_is_gone_from_backend_and_ci():
    assert not (BACKEND_DIR / "app" / "celery_app.py").exists(), "celery_app.py must be deleted"
    config_raw = (BACKEND_DIR / "app" / "config.py").read_text(encoding="utf-8")
    assert "USE_CELERY" not in config_raw
    ci_raw = (BACKEND_DIR.parent / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "USE_CELERY" not in ci_raw
    assert "celery" not in (REPO_DIR / "backend" / "requirements.txt").read_text(encoding="utf-8").lower()


def test_substrate_services_present():
    for name in SUBSTRATE_COMPOSE:
        compose = _compose(name)
        assert "temporal" in compose["services"], f"{name} must ship a Temporal server"
        assert "nazmos-worker" in compose["services"], f"{name} must ship nazmos-worker"


def test_worker_command_targets_temporal_entrypoint():
    for name in SUBSTRATE_COMPOSE:
        compose = _compose(name)
        command = compose["services"]["nazmos-worker"]["command"]
        command = " ".join(command) if isinstance(command, list) else command
        assert "app.orchestration.temporal.worker" in command, (
            f"{name}: nazmos-worker must run the Temporal worker entry point"
        )


def test_business_runtime_sets_use_temporal_true():
    for name in SUBSTRATE_COMPOSE:
        compose = _compose(name)
        api_svc = "api" if "api" in compose["services"] else "backend"
        api_env = compose["services"][api_svc].get("environment", {}) or {}
        worker_env = compose["services"]["nazmos-worker"].get("environment", {}) or {}
        for label, env in ((api_svc, api_env), ("nazmos-worker", worker_env)):
            assert str(env.get("USE_TEMPORAL", "")).lower() == "true", (
                f"{name}: {label} must run with USE_TEMPORAL=true (no local fallback)"
            )


def test_every_workflow_is_registered_and_known():
    from app.orchestration.operations import OPERATION_WORKFLOW
    from app.orchestration.temporal.workflows import WORKFLOWS

    expected_ops = set(OPERATION_WORKFLOW.values())
    missing = expected_ops - set(WORKFLOWS)
    assert not missing, f"workflows missing from WORKFLOWS registration: {sorted(missing)}"

    assert len(WORKFLOWS) == len(set(WORKFLOWS)), "WORKFLOWS keys must be unique"
    for name, cls in WORKFLOWS.items():
        assert cls.__qualname__.endswith("Workflow"), f"{name} -> {cls.__qualname__}"
        assert callable(getattr(cls, "run", None)), f"{name} must expose a workflow run method"


def test_every_activity_has_an_explicit_retry_policy():
    from app.orchestration.retry import POLICY_REGISTRY
    from app.orchestration.temporal.activities import ACTIVITIES

    assert set(ACTIVITIES) == set(POLICY_REGISTRY), (
        "every registered Temporal activity must have an explicit retry policy"
    )


def test_default_schedules_map_to_known_workflows():
    from app.orchestration.operations import OPERATION_WORKFLOW
    from app.orchestration.temporal.schedules import DEFAULT_SCHEDULES

    known = set(OPERATION_WORKFLOW.values())
    assert DEFAULT_SCHEDULES, "default schedules must be defined"
    for wf_name, _spec, _payload in DEFAULT_SCHEDULES:
        assert wf_name in known, f"schedule {wf_name} has no workflow registration"
    schedule_ids = [f"nazm-{wf}" for wf, *_ in DEFAULT_SCHEDULES]
    assert len(schedule_ids) == len(set(schedule_ids)), "schedule ids must be unique"