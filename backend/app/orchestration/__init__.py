"""Temporal-backed durable orchestration for NazmOS execution paths.

Replaces the hand-rolled executors (action_executor, agent_action_executor,
execution_engine) with deterministic workflows and idempotent activities.

Under ``USE_TEMPORAL=True`` (prod) workflows execute via the Temporal server;
under ``USE_TEMPORAL=False`` (CI / SQLite) a local deterministic runner
executes the same workflow+activity code in-process.

The single canonical entrypoints are the three ``run_*`` functions in
``app.orchestration.runner`` — all routers call through them.
"""
from app.orchestration.runner import (
    run_manual_action,
    run_agent_approval,
    run_simulated,
)

__all__ = ["run_manual_action", "run_agent_approval", "run_simulated"]
