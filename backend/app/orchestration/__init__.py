"""Temporal-backed durable orchestration for NazmOS execution paths.

Replaces the hand-rolled executors (action_executor, agent_action_executor,
execution_engine) with deterministic workflows and idempotent activities.

Under ``USE_TEMPORAL=True`` (the default; the only production-legal mode)
workflows execute via the real Temporal substrate (server + NazmOS worker).
Under ``USE_TEMPORAL=False`` (explicitly selected dev / test mode) a local
deterministic runner executes the same composition in-process.

There is NO silent fallback: Temporal unavailability is an explicit
``TemporalExecutionError`` — never a hidden local execution.

The single canonical entrypoints are the ``run_*`` functions in
``app.orchestration.runner`` — all routers call through them.
"""
from app.orchestration.runner import (
    run_manual_action,
    run_agent_approval,
    run_simulated,
)

__all__ = ["run_manual_action", "run_agent_approval", "run_simulated"]
