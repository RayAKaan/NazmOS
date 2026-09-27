# PHASE 2 — BATCH 2 CANONICAL MIGRATION EVIDENCE

- Date: 2026-09-23
- Repo root: `H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED`
- Branch: `phase1-core-infra-replacements` · HEAD: `6078008`
- Purpose: evidence that Batch 2's two migratable surfaces
  (`inventory.stockout_tier`, `inventory.anomaly_triage`) are migrated onto the
  canonical controller choke point with their pre-reqs satisfied, and that
  `procurement.supplier_risk` is deferred per the matrix's own strict rule.

## 1. Batch 2 roster — decision [V]
| Surface | Verdict | Rationale |
|---|---|---|
| `inventory.stockout_tier` | **MIGRATED** | Named tier symbol was missing (pre-req); built `classify_tier` + `INVENTORY_STATUS_TIERS`. Deterministic source = `app.analytics.metrics.classify_status` (canonical, `analytics_service.py:590`). |
| `inventory.anomaly_triage` | **MIGRATED** | Orphan confirmed (zero callers/persists). Pre-req "persist anomalies" satisfied via `app/services/anomaly_triage.py` → `finding_service.create_finding`. Opt-in consumer; no production trigger wired (user-confirmed). |
| `procurement.supplier_risk` | **DEFERRED** | Matrix pre-req = deterministic risk basis from payment history/cost variance; verified absent (no supplier-payment table, no cost-variance computation). On-time/lead-time reliability rubric exists (`product_memory.py:556-582`) but is a documented SUBSTITUTE, not the matrix basis. User decision: defer per strict matrix rule. |

## 2. What was built [V]
1. `app/orchestration/contracts.py` — two new surface contracts:
   - `INVENTORY_STATUS_TIERS = frozenset({"DEAD","CRITICAL","LOW","HEALTHY","OVERSTOCK"})`
   - `ANOMALY_TRIAGE_BUCKETS = frozenset({"SPIKE","DROP"})`
2. `app/analytics/metrics.py` — `status_to_tier()` (fail-closed `KeyError` on
   unknown status) + `classify_tier()`: ONE wrapping call that classifies via
   `classify_status` then maps onto `INVENTORY_STATUS_TIERS`, so the Jev Score
   ladder mirrors the deterministic ladder ("Score must mirror it").
3. `app/services/canonical_controller.py` — `_validate_stockout_tier`,
   `_validate_anomaly_triage` output gates + `canonical_stockout_tier()` and
   `canonical_anomaly_triage()` entry points on the same
   `canonical_decision` → `systemone_reason(shadow=True)` choke point.
4. `app/security/ai_policy.py` — registered the 2 capabilities in
   `AI_CAPABILITIES` + `AI_CAPABILITY_FLAGS` (`_enabled("AI_ENABLED")`).
5. `app/services/anomaly_triage.py` — NEW persistence service (Batch 2 pre-req):
   `persist_anomaly` / `persist_anomalies` write each detector row to the
   canonical `findings` store through `create_finding` (severity spike→high,
   drop→medium; `source="anomaly_detector.zscore"`; evidence = row + threshold +
   detector label). `detect_and_persist()` is the OPT-IN consumer: runs
   `AnomalyDetector`, persists results. INTENTIONALLY not wired to any
   production trigger (Phase 2 shadow-only posture, user-confirmed).

## 3. Verification run [H]
```
cd backend
$env:PYTHONPATH="...\backend"; $env:JEV_ENABLED="false"; $env:USE_TEMPORAL="false"
python -m pytest tests/test_inventory_stockout_tier.py tests/test_anomaly_triage.py -q
```
Result: **15 passed** (8 stockout-tier + 7 anomaly-triage: determinism gate,
shadow parity, contract gate, governance, persistence round-trip, opt-in
consumer, fail-closed mapper). [H]

Combined with Batch 1 + shadow suites:
`tests/test_canonical_controller.py tests/test_provider_failure_tests.py tests/test_shadow_parity.py test_inventory_stockout_tier.py test_anomaly_triage.py`
→ **39 passed**. [H]

Finding-affected sqlite regression (finding_service was touched):
`test_phase12_closed_loop test_phase13_prioritization test_learning_advanced test_learning_engine test_phase5_learning_loop test_phase1_decision_safety_comprehensive`
→ **58 passed, 13 skipped** (skips = Postgres-only). [H]

ai_policy-affected gate suites (DB-free port): **203 passed**. Postgres-backed
tests in these suites now SKIP/ERROR with "Postgres test database is not
available on localhost:5432" because the compose stack is currently DOWN (was up
for the earlier 239-passed baseline). Environment-only; see §5.

`python -m compileall -q app tests` → exit 0. [H]

## 4. Defects found & fixed (non-destructive code fixes)
1. `app/services/finding_service.py::create_finding` — no-id path crashed:
   `UUID(fields.pop("id", None) or _new_uuid())` passed a `UUID` instance into
   `uuid.UUID()` (`AttributeError: 'UUID' object has no attribute 'replace'`).
   Latent: no caller had exercised the no-id path. Fixed to pass the UUID
   through when already a UUID. [FIXED]
2. `app/services/finding_service.py::create_finding` / `verify_finding` —
   Postgres-flavored `CAST(:evidence AS JSON)` silently corrupts JSON payloads
   on SQLite: SQLite resolves the unknown type name "JSON" to NUMERIC affinity,
   coercing non-numeric text to `0` (verified by probe: stored value = `0`).
   Replaced with plain JSON-string binds; `JSON` column type deserializes on
   read (probe round-trip: dict/list restored). Dialect-agnostic, no Postgres
   behavior change. [FIXED]

## 5. Environment note (not a code defect)
The full CI gate (matrix §7.6) needs Postgres for the Postgres-backed security
suites. The compose stack is currently stopped; `docker ps` shows no containers.
The DB-free gate suites (203) pass. The final full regression step of the
mission will restart the stack (non-destructive) before reporting GREEN.

## 6. Batch 2 verdict
**MIGRATED (2) + DEFERRED (1):**
- `inventory.stockout_tier` — canonical tier symbol exists, Jev ladder mirrors
  the deterministic ladder, gate tests green.
- `inventory.anomaly_triage` — ground-truth pre-req satisfied (findings
  persistence, tested), canonical gate green, opt-in consumer only.
- `procurement.supplier_risk` — deferred per MIGRATION_MATRIX §2 strict rule
  (no payment-history/cost-variance basis). Documented with the existing
  on-time/lead-time reliability substitute for a future batch decision.

No production Jev routing — Jev remains shadow-only; deterministic decisions
are always final.