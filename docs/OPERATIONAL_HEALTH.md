# Operational Health

`services/operational_health.py`, exposed at `GET /api/v1/audits/operational-health`.

## Status

- **HEALTHY** — no reconciliation gaps, no failed executions, no stale data.
- **DEGRADED** — stale data or failed executions present.
- **REQUIRES_RECONCILIATION** — terminal actions missing a LearnedOutcome or OutcomeFeedback.

## Data freshness (four-state)

`fresh / aging / stale / unknown`, computed deterministically from `MAX(updated_at)` per
domain (inventory, sales, supplier prices). Thresholds configurable
(`FRESH_*_HOURS`). `unknown` = no timestamp — never fabricated.

## Merchant-facing

A single status line ("Operating normally" / "Some data is stale" / "Attention required").
Operator detail (reconciliation gap counts, per-domain ages) stays in the Ops Console /
operator surface, not the merchant UI.
