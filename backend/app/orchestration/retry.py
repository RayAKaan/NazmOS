"""Explicit Temporal retry policies.

Each policy maps failure classification to deterministic retry parameters.
These are used by Temporal activities to ensure predictable behavior
under failure conditions.

DO NOT rely on Temporal implicit defaults for business-critical activities.
"""

from temporalio import workflow


# ── Policy Classifications ────────────────────────────────────────────

# A. TRANSIENT — temporary infrastructure / network failures
#    → retry with exponential backoff
TRANSIENT = {
    "maximum_attempts": 5,
    "initial_interval_seconds": 1,
    "backoff_coefficient": 2.0,
    "maximum_interval_seconds": 30,
    "description": "Temporary DB connectivity failure, temporary network failure, "
    "temporary external service failure. Retry with backoff.",
}

# B. DETERMINISTIC BUSINESS REJECTION — stock insufficient, budget exceeded,
#    invalid margin, stale action, missing item, failed approval state
#    → do NOT retry indefinitely; return failure immediately
DETERMINISTIC_BUSINESS = {
    "maximum_attempts": 1,
    "initial_interval_seconds": 0,
    "backoff_coefficient": 1.0,
    "maximum_interval_seconds": 0,
    "description": "Insufficient stock, exceeded budget, invalid margin, "
    "stale action, missing item, failed approval state. Do not retry; "
    "return failure to caller for business handling.",
}

# C. AUTHORIZATION FAILURE — user lacks capability, unauthorized
#    → non-retryable, surface error immediately
AUTHORIZATION_FAILURE = {
    "maximum_attempts": 1,
    "initial_interval_seconds": 0,
    "backoff_coefficient": 1.0,
    "maximum_interval_seconds": 0,
    "description": "User lacks capability or is unauthorized. Non-retryable; "
    "require explicit business action to resolve.",
}

# D. INVALID INPUT — malformed request, missing required fields
#    → non-retryable, surface error immediately
INVALID_INPUT = {
    "maximum_attempts": 1,
    "initial_interval_seconds": 0,
    "backoff_coefficient": 1.0,
    "maximum_interval_seconds": 0,
    "description": "Malformed request, missing required fields. Non-retryable; "
    "require request correction before retry.",
}


# Convenience accessors

def transient():
    """Retry policy for transient infrastructure failures."""
    return TRANSIENT


def deterministic_business():
    """Retry policy for deterministic business rejections."""
    return DETERMINISTIC_BUSINESS


def authorization_failure():
    """Retry policy for authorization failures."""
    return AUTHORIZATION_FAILURE


def invalid_input():
    """Retry policy for invalid input."""
    return INVALID_INPUT


# ── Policy Registry ────────────────────────────────────────────────────

# Map activity names to their retry policies.
# Activities should declare their policy; the worker applies it.
# This registry is the canonical source: every activity registered by the
# NazmOS Temporal worker MUST have an explicit classification here (tested in
# tests/test_temporal_retry_wiring.py), so no real activity ever runs with an
# implicit/unknown Temporal retry default.
POLICY_REGISTRY = {
    # ---- Manual path (manual_action) ----
    "revalidate_capability": transient(),
    "validate_action_constraints": deterministic_business(),
    "record_constraint_block": transient(),
    "check_execution_idempotency": transient(),
    "apply_restock": deterministic_business(),
    "apply_price_change": deterministic_business(),
    "apply_discount": deterministic_business(),
    "apply_alert_dismiss": deterministic_business(),
    "record_manual_action": transient(),
    # ---- Agent path (agent_approval) ----
    "record_agent_approval": transient(),
    "agent_mark_executing": transient(),
    "apply_agent_action": deterministic_business(),
    "record_agent_terminal": transient(),
    "record_terminal_outcome": transient(),
    # ---- Simulated path (simulated) ----
    "apply_simulated_execution": deterministic_business(),
}


def get_policy(activity_name: str) -> dict:
    """Retrieve the retry policy for an activity by name."""
    return POLICY_REGISTRY.get(activity_name, transient())