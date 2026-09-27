# PHASE_3K — Owner Loop Console (`app/routers/loop_console.py`)

> Read-only owner surfaces over the loop artifacts. Nothing new is stored, nothing is written. MASTER_PLAN §3.4, G-3K (loop console), §20.

## What was built

Three read-only, owner-gated endpoints under `/api/v1/loop-console`, registered
via the existing router registry (`app/routers/__init__.py` + `app/main.py`):

| Endpoint | Purpose | Data source |
|---|---|---|
| `GET /loop-console/policy` | the deterministic loop contract verbatim: schema version, 21-stage order, rule versions, detection thresholds (≥30d surplus & ≥SAR500, <5d stockout, 22% margin), impact buckets, governance outcomes, recommendation lifecycle + transitions, verification ladder, advisory sources, cycle bounds | `business_loop.contracts`, `business_loop.cycle.CyclePolicy`, `business_loop.opportunity` constants — **no merchant data, DLP-clean** |
| `GET /loop-console/outcomes/verified` | verified outcomes + total verified impact via the **EXISTING** V1 `OutcomeLedger` (`latest_verified_impact`) | `settings.AI_OUTCOME_LEDGER_PATH` (opt-in; empty → fails closed, all-zero, never fabricated) |
| `GET /loop-console/summary` | configured + verified_rows + total verified impact (aggregates only) | same ledger read path |

## Reuse vs parallel

- Reuses the **V1 `OutcomeLedger`** (the loop's only durable artifact) — no new store.
- Reuses the dashboard read-only access pattern verbatim: `depends get_db`,
  `get_current_user`, `assert_business_access` (`routers/dashboard.py:31-47`).
  RLS is automatic (context set from the `business_id` query param).
- Endpoint contract mirrors the loop pure modules — zero drift: the tests assert
  the router code references `RULE_VERSIONS`, `DEFAULT_RULE_OVERRIDES`,
  `CycleStage.ordered()`, `RECOMMENDATION_TRANSITIONS`.

## Security / governance guarantees

- **Owner-gated, not platform-operator**: `assert_business_access` (ownership or
  active team membership) → denials recorded to `audit_log`.
- **Read-only enforced**: router contains only `@router.get` (asserted by test —
  no POST/PUT/PATCH/DELETE anywhere in the file).
- **DLP-clean**: no raw merchant fields read (asserted by test — no `.sku`,
  `"sku"`, `stock_count`, `business_name` access patterns).
- **Fail closed**: unconfigured ledger → `{"configured": False, verified_rows: 0,
  total_verified_impact_sar: 0.0, rows: []}`, never a fabricated number.
- **IDOR guarded**: 3 loop-console read cases added to
  `tests/security/test_idor_cross_tenant.py` READ_CASES + 2 to
  POSITIVE_CONTROL_CASES — attacker reading victim's business → 403/404,
  owner reading own business → 200. Whole suite (26 tests, incl. denial-logging
  proofs) re-ran green against the real Postgres test DB.

## Tests

- `tests/test_loop_console.py` — 7 DB-free module tests (read-only source scan,
  no-parallel-store scan, DLP-clean scan, policy contract verbatim, thresholds,
  fail-closed wording, terminal lifecycle completeness). **7 passed.**
- `tests/test_idor_cross_tenant.py` — extended with the new cases; **26 passed**
  against Postgres (`nazmos:nazmos_v5_dev@localhost:5432/nazmos_test`).

## Status

PASS — read-only owner console over the loop spine, owner-gated, DLP-clean,
zero new durable state.

## Gaps

G-3K closed at the read surface. Live Temporal scheduling + a durable per-cycle
run store remain production-wiring tasks (documented in 3A blockers); the
console intentionally does not fabricate that surface before it exists. [!]