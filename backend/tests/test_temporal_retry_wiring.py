"""Retry wiring: every real Temporal activity is explicitly classified.

Proves the contract that the worker enforces: no activity ever runs under an
implicit Temporal retry default. The behavioral classifications live in
``app.orchestration.retry``; the conversion to real ``RetryPolicy`` objects
lives in ``app.orchestration.temporal.policies``; both must agree cover-for-
cover with the activities registered by the worker.
"""
from __future__ import annotations

import pytest

from temporalio.common import RetryPolicy

from app.orchestration.retry import (
    AUTHORIZATION_FAILURE,
    DETERMINISTIC_BUSINESS,
    INVALID_INPUT,
    POLICY_REGISTRY,
    TRANSIENT,
)
from app.orchestration.temporal.activities import ALL_ACTIVITY_NAMES
from app.orchestration.temporal import policies
from app.orchestration.temporal.activities import ACTIVITIES


def test_every_registered_activity_has_explicit_classification():
    """The worker's activity table and the retry registry are cover-for-cover."""
    assert ACTIVITIES.keys() == POLICY_REGISTRY.keys(), (
        "Activity names registered by the worker must EXACTLY match the retry "
        "registry. Missing from registry: "
        f"{sorted(set(ACTIVITIES) - set(POLICY_REGISTRY))}. "
        f"Unused registry keys: {sorted(set(POLICY_REGISTRY) - set(ACTIVITIES))}."
    )
    assert ALL_ACTIVITY_NAMES == set(POLICY_REGISTRY)


@pytest.mark.parametrize("name", sorted(POLICY_REGISTRY))
def test_every_registry_entry_converts_to_real_policy(name):
    """Every classified activity produces a valid, real Temporal RetryPolicy."""
    policy = policies.ACTIVITY_RETRY_POLICY[name]
    assert isinstance(policy, RetryPolicy)
    assert policy.maximum_attempts >= 1
    assert policy.initial_interval.total_seconds() >= 1.0


@pytest.mark.parametrize("name", ["apply_restock", "apply_price_change", "apply_discount", "apply_agent_action", "apply_simulated_execution"])
def test_mutating_activities_are_deterministic_and_never_retried(name):
    """Exactly-once mutations: their policy requests zero retries."""
    policy = policies.ACTIVITY_RETRY_POLICY[name]
    assert policy.maximum_attempts == 1, (
        f"{name} is a business mutation — it must use maximum_attempts=1 "
        "(never re-run), not Temporal's default unlimited retries."
    )
    assert POLICY_REGISTRY[name] == DETERMINISTIC_BUSINESS


def test_retry_classification_conversion_round_trip():
    """Classification -> RetryPolicy -> attempting-count semantics preserved."""
    assert policies.RC_TRANSIENT.maximum_attempts == TRANSIENT["maximum_attempts"] >= 2
    assert policies.RC_DETERMINISTIC_BUSINESS.maximum_attempts == 1
    assert policies.RC_AUTHORIZATION_FAILURE.maximum_attempts == AUTHORIZATION_FAILURE["maximum_attempts"] == 1
    assert policies.RC_INVALID_INPUT.maximum_attempts == INVALID_INPUT["maximum_attempts"] == 1