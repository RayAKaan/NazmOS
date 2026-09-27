# PHASE 2 — BATCH 3 CANONICAL MIGRATION EVIDENCE

- Date: 2026-09-24
- Repo root: `H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED`
- Branch: `phase1-core-infra-replacements` · HEAD: `6078008`
- Purpose: evidence that Batch 3's three surfaces are migrated onto the
  canonical controller choke point:
  `procurement.reorder_urgency`, `pricing.margin_erosion_risk`,
  `report.finding_priority` — all on the deterministic-wins / Jev-shadow-only
  choke point.

## 1. Batch 3 roster — decision [V]
| Surface | Verdict | Rationale |
|---|---|---|
| `procurement.reorder_urgency` | **MIGRATED** | Deterministic float ladder exists (`procurement_agent` 0.7 if days<5 else 0.4); band symbol was missing (pre-req) — built `REORDER_URGENCY_BANDS` + `reorder_urgency_band()`. Windows stated explicitly in the prompt (days of supply, never days-since-last-sale; DEAD excluded from REORDER; 30-day WS5 dead-by-scan vs `DEAD_STOCK_DAYS=45` dead code). |
| `pricing.margin_erosion_risk` | **MIGRATED** | Deterministic target = canonical `gross_margin_pct` (audit_core `(sell-cost)/sell`); threshold set was scattered (0.15 floor / 0.22 leakage / 0.40 ceiling) — built `MARGIN_EROSION_BANDS` + `margin_erosion_band()` calibrated to it. |
| `report.finding_priority` | **MIGRATED** | Migratable-now: deterministic priority = stored `FindingSeverity` uppercased. Contract `FINDING_PRIORITY_TOKENS` = the 5 severity tokens. Advisory-only until verified outcomes exist (matrix §3). |

## 2. What was built [V]
1. `app/orchestration/contracts.py` — three new surface contracts:
   - `REORDER_URGENCY_BANDS = frozenset({"HIGH", "LOW"})`
   - `MARGIN_EROSION_BANDS = frozenset({"LOW", "MEDIUM", "HIGH"})`
   - `FINDING_PRIORITY_TOKENS = frozenset({"CRITICAL","HIGH","MEDIUM","LOW","INFO"})`
2. `app/services/reorder_urgency.py` (NEW) — `reorder_urgency_band(days_of_supply)`
   → HIGH if canonical days-of-supply < 5 else LOW (None → LOW: no projection,
   never fabricate urgency). Docstring states the window decisions:
   days-of-supply vs days-since-last-sale; WS5 dead-by-scan `<1 unit / 30d`;
   DEAD excluded from REORDER (`ab_decision_framework`); unused
   `DEAD_STOCK_DAYS = 45` explicitly NOT consulted.
3. `app/services/margin_erosion.py` (NEW) — `margin_erosion_band(margin_ratio)`
   → LOW (<0.15, margin_agent/MARGIN_EROSION floor), MEDIUM (<=0.40, ceiling),
   HIGH (>0.40). Band = margin MAGNITUDE (LOW = most eroded); leakage target
   0.22 cited in prompts, not a band edge.
4. `app/services/finding_service.py` — `finding_priority_token(severity)` →
   severity uppercased, default MEDIUM on None.
5. `app/services/canonical_controller.py` — docstring + Batch 3 surfaces; five
   new capability defaults; `_validate_reorder_urgency`,
   `_validate_margin_erosion`, `_validate_finding_priority` output gates;
   `canonical_reorder_urgency()`, `canonical_margin_erosion()`,
   `canonical_finding_priority()` entry points on the same
   `canonical_decision` → `systemone_reason(shadow=True)` choke point.
6. `app/security/ai_policy.py` — registered the 3 capabilities
   (`supply.reorder_urgency` purpose "score the reorder urgency ladder over
   days of supply", `pricing.margin_erosion_risk`, `report.finding_priority`)
   + `AI_CAPABILITY_FLAGS` (`_enabled("AI_ENABLED")`).

## 3. Defect found & fixed (non-destructive test-infra fix)
The process-wide `GLOBAL_AI_BUDGET` singleton's autouse fixture in every test
module only reset `calls_this_audit` (`begin_audit()`), leaving `calls_today`
(cap 25) to accumulate across a combined suite. In a 53-test combined run the
daily cap was exhausted mid-suite, so late contract-gate tests fell to
budget-exhaust fallback and their Jev-suggestion assertions failed (5 failures
seen before the fix). Fix: added `AIBudget.reset()` zeroing ALL counters and
switched every autouse fixture to call it — suites are now order-independent.
Runtime behavior unchanged (production code never calls `reset()`). [FIXED]

## 4. Verification run [H]
```
cd backend
$env:PYTHONPATH="...\backend"; $env:JEV_ENABLED="false"; $env:USE_TEMPORAL="false"
python -m pytest tests/test_canonical_controller.py tests/test_provider_failure_tests.py \
    tests/test_shadow_parity.py tests/test_inventory_stockout_tier.py \
    tests/test_anomaly_triage.py tests/test_batch3_canonical_surfaces.py -q
```
Result: **53 passed** — Batch 1 (9) + Batch 2 (15) + Batch 3 (14) + shadow
parity/provider failure (15 unit/parity/availability gates), combined, after the
budget-reset fix. [H]

Batch 3 alone: **14 passed** (band helpers mirror ladders/thresholds, three
determinism gates with source=fallback + ledger rows, three shadow-parity
agree/dissent, three out-of-contract gates → JEV_OUT_OF_CONTRACT, two
deterministic contract-enforcement → CanonicalControllerError). Reported
standalone: `14 passed`; combined: green. [H]

Gate regression (DB-free; ai_policy + finding_service touched):
`tests/security tests/phase4 tests/test_phase5.py` → **203 passed, 29 skipped,
7 errors**. Every skip and error is the SAME environmental signature as before
Batch 2/3: "Postgres test database is not available on localhost:5432" skips
(test_approval_authorization, test_idor_cross_tenant, test_phase5) and
`test_celery_rls_tenant_context.py` setup `ConnectionRefusedError` — the compose
stack is down. No new failures from Batch 3 code. [H]

`python -m compileall -q app tests` → exit 0. [H]

## 5. Environment note
The Postgres-backed gate suites need the compose stack up. `docker ps` shows no
containers; the DB-free gate port is green (203 passed). The final full
regression step of the mission restarts the stack (non-destructive) before
reporting GREEN.

## 6. Batch 3 verdict
**MIGRATED (3/3):**
- `procurement.reorder_urgency` — deterministic urgency band exists over
  days-of-supply; prompt states the windows (`DEAD_STOCK_DAYS=45` dead code
  avoided; 30-day WS5 dead-by-scan; DEAD excluded); gates green.
- `pricing.margin_erosion_risk` — deterministic band calibrated to the
  codebase's real thresholds (0.15/0.22/0.40); gates green.
- `report.finding_priority` — severity contract as the priority token;
  advisory-only (no verified-outcome calibration yet); gates green.

No production Jev routing — Jev remains shadow-only; deterministic decisions
always final.