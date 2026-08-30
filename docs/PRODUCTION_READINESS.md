# Production Readiness

Status: **Phase 11.** This documents what is real vs estimated vs unavailable.

## Proven (automated tests)

- Deterministic executors + policy gate (agent → policy → executor, never agent → executor).
- Idempotent learning (unique constraints + ON CONFLICT) and reconciliation (hourly Celery).
- Per-finding impact attribution (`direct/partial/business_level/estimated/unattributable`).
- Strategy performance + recency + regime + decision scoring (deterministic).
- Root-cause (stockout/dead-stock/margin) with explicit `uncertain` when unsupported.
- Postgres concurrency suite (gated, runs in CI).

## Estimated (labeled, never presented as realized)

- Inference cost (`estimated_cost_usd`) — no billing integration.
- Expected vs estimated impact (always distinct from observed).

## Unavailable (not fabricated)

- Supplier purchase-cost webhooks (Foodics/Salla emit sales orders only).
- Actual provider billing.
- Cross-merchant aggregate learning.

## Safety floors (immutable from the frontend)

Min confidence, risk-escalation thresholds (SAR 5k/20k, only raisable), pricing dial cap,
mandatory human approval for financial movements.
