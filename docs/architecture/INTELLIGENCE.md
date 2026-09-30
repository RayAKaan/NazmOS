# NazmOS Intelligence — Architecture

> Canonical reference for the Intelligence layer.
> This document is the single source of truth; per-phase reports are not kept.

## 1. Purpose

NazmOS is one Business Operating System with three capability layers:

| Layer | Question it answers | Owner |
|---|---|---|
| **Orbit** — See | What *is* the business? | ingestion, canonical state, Financial X-Ray, evidence, history |
| **Intelligence** — Understand | What does it *mean*, and what should we consider? | context, monitoring, signals, root cause, impact, recommendations, advisory, decision candidates, alerts, Owner Copilot |
| **Loop** — Improve | What actually *happens*, and did it work? | governance, approval, execution, reconciliation, measurement, verification, learning |

**Intelligence owns understanding. It owns no execution authority.**

## 2. Authority boundaries

```
Orbit (truth)  →  Intelligence (understanding)  →  Governance (permission)  →  Loop (execution)
```

| Boundary | Rule |
|---|---|
| Orbit is authoritative | Intelligence consumes Orbit's canonical state; it never re-derives business truth from raw uploads. |
| Intelligence does not execute | No Intelligence code path may mutate external business systems or dispatch an action. |
| Governance owns permission | Intelligence emits `DecisionCandidate`; only Governance may authorize it. |
| Loop owns outcomes | `APPROVED / EXECUTED / VERIFIED` impact and learning eligibility are produced by the Loop, never by Intelligence. |
| Jev is advisory | Jev may add confidence, an alternative, or a challenge. It cannot authorize, execute, mutate, bypass governance, or invent evidence. |
| Learning is verified-only | Intelligence may *consume* verified outcomes; it never creates learning authority. |

## 3. Data flow

```
                 ┌──────────────────────────────────────┐
                 │ Orbit — canonical state              │
                 │ BusinessSnapshot / OrbitAuditResult  │
                 │ (health_breakdown, exposures,        │
                 │  findings, opportunities,            │
                 │  limitations, evidence)              │
                 └──────────────────┬───────────────────┘
                                    │  state_version (= Orbit audit_id)
                                    ▼
                 ┌──────────────────────────────────────┐
                 │ Intelligence                        │
                 │                                      │
                 │  BusinessContext      (projection)  │
                 │        ↓                             │
                 │  DetectorRegistry  → Signal[]       │
                 │        ↓                             │
                 │  RootCauseEngine  → RootCause[]     │
                 │        ↓                             │
                 │  ImpactEngine     → ImpactEstimate[]│
                 │        ↓                             │
                 │  RecommendationEngine                │
                 │        ↓                             │
                 │  Advisory (Jev, bounded)            │
                 │        ↓                             │
                 │  DecisionCandidate[] → Governance    │
                 │        ↓                             │
                 │  Alert[]  ·  Owner Copilot          │
                 └──────────────────┬───────────────────┘
                                    ▼
                          Governance → Loop
                                    │
                                    ▼
                          VERIFIED OUTCOMES ──► Intelligence (next run)
```

Every stage preserves `business_id`, `state_version`, `evidence_ids`, `freshness`, `confidence`, timestamps, provenance, and a contract version.

## 4. Contracts

Defined once in `backend/app/services/intelligence/contracts.py` and mapped to the
wire in `backend/app/schemas/intelligence.py` + `app/services/intelligence/api_mappers.py`.

| Contract | Purpose | Key invariants |
|---|---|---|
| `BusinessContext` | Projection of Orbit + Loop state | never invents values; carries `state_version`, `data_freshness`, `data_quality_score` |
| `Signal` | Deterministic detection | `baseline_formula` is always populated; insufficient data yields a marker, not a fake signal |
| `RootCause` | Cause hypothesis | `support_level` ∈ `observed / supported / possible / unknown`; records counter-evidence |
| `ImpactEstimate` | Quantified impact | `kind` ladder `POTENTIAL → EXPECTED → APPROVED → EXECUTED → VERIFIED`; exposes formula + assumptions |
| `Recommendation` | Candidate action | `action_type` from `CANONICAL_ACTION_TYPES`; scored by the centralized scorer |
| `AdvisoryResult` | Jev advisory | `source` is exact — never labels fallback as Jev |
| `DecisionCandidate` | Handoff to Governance | has no `EXECUTED`/`VERIFIED` status at all |
| `Alert` | Owner-facing alert | deterministic `fingerprint` for deduplication |
| `IntelligenceRun` | One evaluation result | `status` ∈ `running / completed / partial / failed`, with `warnings` + `failed_detectors` |
| `CopilotAnswer` | Owner explanation | always cites sources/evidence; says "insufficient data" rather than inventing |

### Freshness

`FRESH · STALE · PARTIAL · MISSING · CONFLICT · UNKNOWN`

`evaluate_freshness()` derives freshness from Orbit's own audit timestamp
(>4h ⇒ `STALE`, >24h ⇒ `MISSING`). **Missing is never rendered as zero, and stale
is never rendered as fresh.**

## 5. Baselines

`app/services/intelligence/baseline.py` provides an explicit, versioned baseline
abstraction: `CURRENT_PERIOD`, `PREVIOUS_PERIOD`, `ROLLING_MEAN`, `ROLLING_MEDIAN`,
`TREND`, `EXPECTED_RANGE`, `THRESHOLD`, `SEASONAL_BASELINE`.

Every baseline reports `available=False` plus a machine-readable `reason` when there
is not enough history, and every signal carries `baseline_formula` describing how
its deviation was computed. A zero baseline yields absolute deviation only — the
percentage is *undefined*, not reported as a fake `0%`.

## 6. Detectors

`app/services/intelligence/signals.py` — deterministic, versioned
(`DETECTOR_VERSION`), individually testable, and forbidden from calling Jev or
mutating state (enforced by a test that greps detector source).

Detectors read only Orbit's canonical output: `health_breakdown.*` domain scores,
`exposures.*`, `limitations.*`, `findings[]`, and the historical audit series.

| Detector | Domain | Detects |
|---|---|---|
| `health_deterioration` | financial | overall health regression vs. Orbit history |
| `sales_trend` | sales | sales-health regression |
| `revenue_decline` | sales | revenue-at-risk level (explicitly *not* a decline without a prior period) |
| `margin_erosion` | margin | margin-health regression / low margin |
| `excess_inventory` | inventory | trapped capital |
| `stockout_risk` | inventory | inventory-health weakness |
| `procurement_health` | procurement | procurement-health weakness |
| `profit_at_risk` | financial | gross profit at risk |
| `data_quality_gap` | data_quality | unknown/estimated Orbit inputs |

Detectors are failure-isolated: a raising detector is recorded in
`failed_detectors` and yields a `PARTIAL` run rather than a fabricated clean result.

## 7. Reused authorities (no second brain)

The canonical layer **reuses** existing authorities instead of re-implementing them:

| Concern | Authority reused |
|---|---|
| Business truth | `app/services/orbit_contracts.py`, `audit_persistence.py` |
| Latest Orbit state | `AuditPersistenceService.get_latest_audit_for_business()` (added; Orbit reads its own tables) |
| Action vocabulary | `app/orchestration/contracts.CANONICAL_ACTION_TYPES` + `app/services/action_registry.ACTION_REGISTRY` |
| Recommendation scoring | `app/services/decision_scoring.compute_recommendation_score()` (single formula) |
| Root-cause taxonomy | `app/services/canonical_controller.ROOT_CAUSE_BUCKETS` |
| Jev advisory + validation | `app/services/canonical_controller.canonical_decision()` → `ai_gateway.systemone_reason` → `jev.consult` |
| Privacy / DLP | `app/security/privacy_firewall.py`, `ReasoningCapsule` |
| Governance policy | `app/services/business_loop/governance.evaluate_governance()` |
| Execution | `app/orchestration/runner.py` (**never** called from Intelligence) |
| Verified outcomes | `app/services/business_loop/outcomes.py`, `outcome_ledger.py` |

## 8. Jev relationship

```
deterministic recommendation
   → advisory payload (pre-banded, no identifiers/exact amounts)
   → privacy firewall → ReasoningCapsule
   → canonical_controller (verify-then-finalize, shadow mode)
   → ai_gateway.systemone_reason
   → Jev
   → typed validation (out-of-contract suggestions discarded)
   → AdvisoryResult
   → DecisionCandidate (deterministic value always wins)
```

- Advisory is **opt-in** (`enable_advisory=False` by default), so a deterministic run
  never depends on external AI availability.
- Failure, policy blocks, budget exhaustion, transport errors and out-of-contract
  suggestions all yield `AdvisorySource.DETERMINISTIC_ONLY` — never `JEV`.
- Jev confidence is reported as *advisory* confidence and never merged into the
  deterministic evidence confidence.
- Advisory is bounded (`max_consultations`, default 3).

## 9. Governance handoff

`DecisionCandidate` carries the deterministic basis, the advisory (if any), expected
impact, evidence, constraints, and an expiry. `handoff_to_governance()` calls the
canonical `evaluate_governance()` with the **registry action key** and records the
verdict. Intelligence never overrides it.

Because `DecisionCandidateStatus` contains no `EXECUTED`/`VERIFIED` member, the
Intelligence layer *structurally cannot* claim an action ran or recovered money.

## 10. API

`backend/app/routers/intelligence_v2.py` — one canonical surface:

```
GET  /api/v1/intelligence/context
GET  /api/v1/intelligence/signals
GET  /api/v1/intelligence/root-causes
GET  /api/v1/intelligence/impacts
GET  /api/v1/intelligence/recommendations
GET  /api/v1/intelligence/recommendations/{id}
GET  /api/v1/intelligence/decisions
GET  /api/v1/intelligence/decisions/{id}
GET  /api/v1/intelligence/alerts
GET  /api/v1/intelligence/alerts/{id}
POST /api/v1/intelligence/monitor
POST /api/v1/intelligence/analyze
POST /api/v1/intelligence/copilot
```

`/analyze` is an alias of the canonical pipeline, not a second engine.

### Deliberately removed

| Endpoint | Reason |
|---|---|
| `POST /intelligence/execute` | Execution is a Loop concern. It bypassed Governance/Approval. Now `410 Gone`. |
| `GET /intelligence/execution-jobs/{id}` | Loop concern. Now `410 Gone`. |
| `POST /intelligence/predict` | Returned hardcoded `confidence: 0.95` with the current value echoed back, and `0.0` when no data existed (missing-as-zero). Real forecasting lives behind `/api/v1/forecast`. Now `410 Gone`. |

### Security & error semantics

- Every route requires authentication and authorizes via the shared
  `assert_business_access` gate (the same gate that establishes the RLS tenant
  context) — one tenant-isolation path, no bespoke checks.
- `401` unauthenticated · `403`/`404` unauthorized or not-visible (never discloses
  whether another tenant's record exists) · `422` invalid input · `409` stale/conflict
  (e.g. no canonical Orbit state) · `429` rate limited where applied.
- Bounded pagination (`limit ≤ 200`).
- Read endpoints run the pipeline but never write and never execute.

## 11. Persistence

The Intelligence layer is deliberately **stateless**: a run is a deterministic
projection of Orbit state, so artifacts are reproducible and history is never
rewritten. This avoids duplicating Orbit's audit history and satisfies the versioning
requirement — `detector_version`, `analysis_version`, `calculation_version`,
`recommendation_version`, and the contract versions make old and new results
distinguishable.

No new Intelligence tables were created, deliberately: `findings`, `audit_runs`,
`impact_ledger`, `business_goals`, `learned_outcomes`, `cycle_runs`,
`outcome_feedback`, and `agent_actions` already exist and remain authoritative.
Intelligence references them by id rather than re-persisting the same facts.

Orbit's tables gained declarative models in `app/database/models.py` mirroring
`ff16_orbit_tables` exactly, so the schema is constructible from ORM metadata in
tests and Orbit is a first-class part of the data model.

## 12. State invalidation

`recommendations.is_stale(rec, context)` is true when the recommendation's
`state_version` differs from the current Orbit audit (material state change) or it
has expired. `governance_requirements` records
`data_freshness_<state>_revalidation` for any recommendation built on non-fresh
evidence, so the Loop must revalidate before executing.

## 13. Duplicate suppression

| Artifact | Fingerprint over |
|---|---|
| `Signal` | `business_id, signal_type, resource, detector_version, state_version` |
| `Alert` | `business_id, alert_type, signal_type, resource, detector_version` |

Alert fingerprints deliberately **exclude** `state_version` so the same underlying
issue stays one alert across re-audits. `run_is_idempotent()` compares *material*
identity (excluding surrogate ids/timestamps), so repeated monitoring converges
rather than multiplying.

## 14. Confidence & uncertainty

Confidence is derived, never invented: detector confidence scales with baseline
sample size (e.g. 0.8 with ≥3 prior audits, 0.6 otherwise); root-cause confidence
comes from support level (observed 0.9 → unknown 0.0); impact is discounted by
support (`observed 1.0`, `supported 0.8`, `possible 0.4`, `unknown 0.0` — an UNKNOWN
cause produces **no** impact at all). When evidence is insufficient the result is
`DO_NOT_ACT`/`REVIEW`, never fabricated certainty.

## 15. Failure behaviour

| Failure | Behaviour |
|---|---|
| No Orbit state | Run `FAILED` with `orbit_state_unavailable`; API returns `409`. Never a zero-valued state. |
| Detector raises | Recorded in `failed_detectors`; run is `PARTIAL`. |
| No detector can judge | Run is `PARTIAL` with `insufficient_data:*` warnings — not a clean bill of health. |
| Jev unavailable / policy-blocked / budget-exhausted | Advisory becomes `DETERMINISTIC_ONLY`; run still completes. |
| Recommendation base unavailable | Impact is not quantified (no estimate emitted). |
| Impact arithmetic error | Recorded as a warning; the rest of the run survives. |

No silent fallbacks: database failure never becomes empty data, Jev failure never
becomes Jev confidence, missing never becomes zero, stale never becomes fresh, and
unknown cause never becomes known cause.

## 16. Testing

```bash
cd backend
python -m compileall -q app tests

# deterministic, DB-free
USE_TEMPORAL=false python -m pytest tests/test_intelligence_layer.py -q

# API contract + tenant isolation (needs Postgres)
USE_TEMPORAL=false TEST_DATABASE_URL=postgresql+asyncpg://nazmos:nazmos_dev@localhost:5432/nazmos_test \
  python -m pytest tests/test_intelligence_api.py -q
```

Covered invariants include: missing ≠ zero, stale ≠ fresh, potential ≠ verified,
Jev never authoritative, correlation ≠ certainty, invalid actions cannot become
recommendations, cross-tenant access denied, detectors never call AI, and repeated
monitoring converges.

## 17. Known limitations

- **Detectors are bounded by what Orbit persists.** Orbit's audit history stores
  `health_score` and `health_breakdown`, but not per-period exposure series, so
  exposure-trend baselines report insufficient data until Orbit persists them.
- **Advisory is off by default.** Enable per-request via `enable_advisory`.
- **Legacy Intelligence endpoints remain** for paths the canonical API does not yet
  cover (business-memory documents, knowledge-graph exploration, plans, simulations,
  event derivation/timeline). They are being migrated onto the canonical contracts;
  the dangerous ones (execution, fake prediction) are already removed.
