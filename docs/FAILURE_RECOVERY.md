# Failure Recovery

What happens when each stage fails, and how the system recovers without corrupting state.

| Stage | On failure | Recovery |
|---|---|---|
| Audit | `AuditRun.status=failed`, error recorded | re-run (idempotent per domain) |
| Finding creation | domain adapter logs + skips | re-audit |
| Root cause | returns `uncertain` | n/a (never fabricates) |
| Recommendation | deterministic score; no LLM dependency | n/a |
| Policy | fail-closed (no auto-execution) | approval required |
| Execution | executor returns `{executed:False}` | no false success |
| Verification | fallback to business-level attribution, labeled | reconciliation |
| Impact recording | idempotent per (action, attribution) | reconciliation |
| Learning write | `ON CONFLICT` idempotent | `learning_reconciliation` (hourly Celery) |
| Graph projection | best-effort (never fails the action) | re-projection on event replay |
| Report | returns partial/empty fields | re-run |

## Invariant

A technical failure is NEVER converted into a successful business outcome, realized revenue,
or verified impact. Learning gaps are repaired deterministically; business outcomes are never
fabricated.
