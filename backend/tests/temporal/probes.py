"""Test-only retry probes for proving REAL server-side retry wiring.

These are deliberately vanilla activities/workflows with explicit RetryPolicies
so the integration suite can assert that Temporal actually retried (transient)
exactly as many times as the class says, and no more (deterministic). They are
registered ONLY through ``build_worker(extra_activities=..., extra_workflows=...)``
and live in the test tree — never in the production service.
"""
from __future__ import annotations

import datetime

from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

PROBE_TRANSIENT = RetryPolicy(
    maximum_attempts=2,
    initial_interval=datetime.timedelta(seconds=1),
    backoff_coefficient=2.0,
)
PROBE_NO_RETRY = RetryPolicy(
    maximum_attempts=1,
    initial_interval=datetime.timedelta(seconds=1),
)
_START_TO_CLOSE = datetime.timedelta(seconds=30)


@activity.defn(name="retry_probe")
async def retry_probe(payload: dict) -> dict:
    """Fail until ``activity.info().attempt`` exceeds ``fail_through_attempt``."""
    info = activity.info()
    fail_through = int(payload.get("fail_through_attempt", 1))
    if info.attempt <= fail_through:
        raise ApplicationError(f"transient probe failure on attempt {info.attempt}", type="TRANSIENT_PROBE")
    return {"attempts_seen": info.attempt}


@workflow.defn(name="retry_probe_transient")
class RetryProbeTransientWorkflow:
    @workflow.run
    async def run(self, req: dict) -> dict:
        try:
            res = await workflow.execute_activity(
                "retry_probe",
                req,
                start_to_close_timeout=_START_TO_CLOSE,
                retry_policy=PROBE_TRANSIENT,
            )
            return {"ok": True, "attempts": res["attempts_seen"]}
        except ActivityError as exc:
            cause = exc.cause if isinstance(exc.cause, ApplicationError) else exc
            return {"ok": False, "error": str(cause)}


@workflow.defn(name="retry_probe_no_retry")
class RetryProbeNoRetryWorkflow:
    @workflow.run
    async def run(self, req: dict) -> dict:
        try:
            res = await workflow.execute_activity(
                "retry_probe",
                req,
                start_to_close_timeout=_START_TO_CLOSE,
                retry_policy=PROBE_NO_RETRY,
            )
            return {"ok": True, "attempts": res["attempts_seen"]}
        except ActivityError as exc:
            cause = exc.cause if isinstance(exc.cause, ApplicationError) else exc
            return {"ok": False, "error": str(cause)}


PROBE_ACTIVITY_FUNCTIONS = [retry_probe]
PROBE_WORKFLOWS = [RetryProbeTransientWorkflow, RetryProbeNoRetryWorkflow]