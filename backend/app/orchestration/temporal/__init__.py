"""Temporal substrate for NazmOS execution.

A thin durable-execution layer: workflows (skeletons only) + activities
(transport adapters over the canonical NazmOS business functions) + worker.
Business semantics, inventory/financial truth, authz, approvals, constraints,
guards, idempotency and provenance ALL remain in the app layer — Temporal owns
only durable scheduling, retries, and replay.
"""