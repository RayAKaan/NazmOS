"""Temporal retry-policy wiring for NazmOS execution activities.

The behavioral retry classifications live in ``app.orchestration.retry``
(TRANSIENT / DETERMINISTIC_BUSINESS / AUTHORIZATION_FAILURE / INVALID_INPUT)
and are the single source of truth. This module converts those classifications
into real ``temporalio.common.RetryPolicy`` objects and exposes the canonical
activity-name → policy mapping that the worker and the workflow definitions
both consume, so the configured policy is literally the policy attached at
every activity invocation.
"""
from __future__ import annotations

import datetime

from temporalio.common import RetryPolicy

from app.orchestration.retry import (
    AUTHORIZATION_FAILURE,
    DETERMINISTIC_BUSINESS,
    INVALID_INPUT,
    POLICY_REGISTRY,
    TRANSIENT,
    get_policy,
)

# Temporal requires initial_interval > 0 even when maximum_attempts == 1.
# ``maximum_attempts=1`` is the "never retry" carrier for deterministic
# business rejections; the interval floor makes the policy valid.
_MIN_INTERVAL_S = 1.0


def to_retry_policy(policy: dict) -> RetryPolicy:
    """Convert a retry classification dict to a real Temporal RetryPolicy."""
    max_interval_s = float(policy.get("maximum_interval_seconds") or 0)
    return RetryPolicy(
        maximum_attempts=int(policy["maximum_attempts"]),
        initial_interval=datetime.timedelta(
            seconds=max(_MIN_INTERVAL_S, float(policy["initial_interval_seconds"]))
        ),
        backoff_coefficient=float(policy.get("backoff_coefficient", 2.0)),
        maximum_interval=(
            datetime.timedelta(seconds=max_interval_s)
            if max_interval_s > _MIN_INTERVAL_S
            else None
        ),
    )


# Canonical RetryPolicy instances per classification.
RC_TRANSIENT = to_retry_policy(TRANSIENT)
RC_DETERMINISTIC_BUSINESS = to_retry_policy(DETERMINISTIC_BUSINESS)
RC_AUTHORIZATION_FAILURE = to_retry_policy(AUTHORIZATION_FAILURE)
RC_INVALID_INPUT = to_retry_policy(INVALID_INPUT)

# activity_name -> RetryPolicy, derived from the canonical registry.
ACTIVITY_RETRY_POLICY: dict[str, RetryPolicy] = {
    name: to_retry_policy(policy) for name, policy in POLICY_REGISTRY.items()
}


def activity_retry_policy(activity_name: str) -> RetryPolicy:
    """Return the explicit Temporal RetryPolicy for ``activity_name``.

    Unknown activity names resolve to TRANSIENT (conservative — never to zero
    retries) but the completeness test (tests/test_temporal_retry_wiring.py)
    guarantees every registered activity is an explicit registry member.
    """
    return ACTIVITY_RETRY_POLICY.get(activity_name, RC_TRANSIENT)