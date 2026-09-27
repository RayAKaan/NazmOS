# NazmOS 2.0 — Jev-Powered Retail Intelligence & Recovery Platform

**Master Plan (grounded in Phase 0 reality audit)**

Version: 1.0 — authored from the Phase 0 reality audit of commit `208ca04` (branch `phase1-core-infra-replacements`) plus the uncommitted working tree as of 2026-09-20.

## 1. Vision

Transform NazmOS from a **deterministic-only decision platform** into a **deterministic-plus-Jev intelligence platform**: the same business logic, the same governance, and the same execution substrate — but with Jev (TypeSafe's System One typed-decision model) as a **shadow adviser and structured-judgment provider** on a strict subset of decision surfaces, under explicit guardrails.

Jev shall be a **decision adviser, never a financial authority**:
- Jev does NOT become the source of financial truth (velocity, SAR values, forecasts, metrics, business rules).
- Jev does NOT bypass governance (owner, Shariah, permissions). Unknown provider behavior ≠ permission; Jev never declares Shariah compliance.
- Jev does NOT execute. Temporal + the single orchestration dispatcher remain the ONLY execution substrate.
- Jev's typed outputs (`Choice | Score | Noul`) are consumed as enriched evidence, cross-checked against the deterministic decision, and logged with provenance.

## 2. Guiding Constraints (non-negotiable)

1. **Financial truth stays deterministic.** Money-critical metrics must remain computable, auditable, and byte-identical from the deterministic core regardless of AI availability.
2. **Execution stays Temporal.** Durable execution only. The local runner is for tests/CI only — never a production fallback; `TemporalExecutionError` and startup fail-closed checks remain.
3. **Governance precedes intelligence.** Every action still passes capability check → constraint check → idempotency → apply → record. Autonomy dial semantics are unchanged. Jev evidence kan add context but cannot unlock permissions.
4. **Verified outcomes ≠ recommendation ≠ execution.** Jev recommends; governance disposes; Temporal executes; outcome learning records verified results.
5. **Migration discipline. EXACTLY THREE replacements per batch.** No more, no fewer — each batch is fully tested and accepted before the next.
6. **Preserve existing systems.** No removal of temporal/, security/ stack, RLS, agents, or their tests. Everything Jev adds is additive.
7. **Evidence labels everywhere.** Every claim in deliverable docs is marked [VERIFIED] / [HISTORICAL] / [INFERRED] / [UNVERIFIED] / [BLOCKED] / [NOT PRESENT]. Nothing fabricated.

## 3. Phases and Execution Order

| Phase | Name | Goal | Exit condition |
|---|---|---|---|
| 0 | Reality audit (this phase) | Evidence-backed truth of the repo today | 9 deliverables at repo root + final report |
| 1 | Finish foundation acceptance | Repo compiles; all gates green; Phase 2B vel convergence + 2C acceptance executed | CI-equivalent all green; RLS+Temporal gate passes |
| 2 | Jev provider integration | Provable, isolated Jev transport behind `ai_gateway.reason` | `systemone` transport + `JevTransport` in ai_adapter, tests green (mock + opt-in real) |
| 3 | Decision & evidence contracts | Unified `DecisionEvidence` / proof contracts for every frozen decision record | All 9 batch surfaces emit schema-versioned evidence |
| 4 | Governance integration | Evidence pipeline + capability/budget/capsule/audit wiring | Jev call lifecycle fully audited under existing policy |
| 5 | Jev workload migration (shadow) | 3+3+3 typed replacements shipped in shadow mode across batches | Migration matrix fully executed; deterministic outcome is authoritative |
| 6 | Unified business state | Single state snapshot feeding all intelligence | One snapshot → decision, evidence, outcome all consistent |
| 7 | Continuous intelligence | Recurring Jev evaluation with caching + budget governance | Scheduled/streamed evaluation within budget |
| 8 | Outcome feedback & memory | Verified outcomes refine Jev prompts via `outcome_feedback_contract` | Learning loop consumes verified outcomes, not Jev output |
| 9 | Cross-domain decisions + Recovery Match | Jev advises across domains; Recovery Match evidence-enriched | Cross-domain recommendations carry passing guardrails |
| 10 | Controlled autonomy | Autonomy dial starts to act on trusted Jev evidence (inform→approval→auto) | Each dial step gated by tests proving deterministic primacy |
| 11 | Production & commercial readiness | Observability, cost guardrails, docs, rollout | Exit report + review; no regressions |

## 4. Migration Matrix (the 9 replacements, exactly 3 per batch)

| Batch | Surface | Mapping |
|---|---|---|
| 1 | `recovery.rank` | Choice over rank buckets |
| 1 | `recovery.action_type` | Choice over canonical action types (contract set) |
| 1 | `audit.root_cause_bucket` | Choice over root-cause taxonomy |
| 2 | `inventory.stockout_tier` | Score over urgency ladder (must remain aligned to deterministic classify_status) |
| 2 | `inventory.anomaly_triage` | Choice + Score; note today this logic is orphaned (no consumer persists it) |
| 2 | `procurement.supplier_risk` | Score over 3-level risk rubric (deferred from NB if no deterministic ground truth) |
| 3 | `procurement.reorder_urgency` | Score over urgency ladder |
| 3 | `pricing.margin_erosion_risk` | Score over erosion rubric (needs deterministic ground-truth target) |
| 3 | `report.finding_priority` | Choice over severity tiers (tie to `report.finding_priority`/severity contract) |

**Deferred (never batched, documented only):** `procurement.moq_risk`, `pricing.owner_band_eligibility` (deterministic rule per plan), `governance.shariah_review_triage` (governance must never delegate to a model), `finance.cash_action_priority`, `approval.routing_priority`, `approval.urgency_score`.

## 5. Jev Integration Contract

- Endpoint: `POST https://api.typesafe.ai/v1/systemone` (model `jev-latest`, or pinned `jev-1.13.0` in production).
- Typed answers: `Choice` (`choice`, `probabilities`, `confidence`), `Score` (`score`, `legend`, `probabilities`, `confidence`), `Noul` (`noul` only — no confidence field).
- Wire via `ai_gateway.reason()` — the single policy-checked AI interface — extended with a Jev (SystemOne) transport in `app/security/ai_adapter.py`.
- Capsule: build via `ReasoningCapsule` only; `capsule.for_prompt()` is the ONLY outbound serializer; DLP-clean.
- Budget: `GLOBAL_AI_BUDGET` governs every Jev call; fallback is the deterministic decision (never a freeform model).
- Behavior when Jev unavailable/budget-exhausted: deterministic decision is authoritative; explicit audit event; no silent degradation.

## 6. Hard Governance Rules for Jev

- Jev output is always treated as **untrusted evidence** until the output-gate validates it.
- No Jev output (Choice/Score/Noul) can trigger a business action directly. All actions flow through `runner._dispatch` with capability+constraint+idempotency checks.
- `governance.shariah_review_triage` and `pricing.owner_band_eligibility` remain 100% deterministic. Documented rationale: governance/permission boundaries must not be delegated to a model whose lifecycle can change behavior.
- Thresholds for Score/Noul are chosen from deterministic ground truth; a dead band is kept where nothing acts automatically.
- Every Jev answer is persisted (via `ai_reasoning_requests` and decision evidence) with model version, capsule hash, provider, latency, and source label.

## 7. Data & Security Boundaries

- Tenant isolation is enforced by Postgres RLS; Jev traffic is tenant-scoped in the audit layer, never in the capsule (capsule carries no business_id by design).
- Capsule content: opaque refs + banded signals only. Never send SKUs, business/product ids, exact SAR, stock counts, budgets, margins, or outcomes.
- Encrypted columns (`EncryptedText`) remain untouched.
- No secrets in code; `TYPESAFE_API_KEY` lives in environment, validated at startup, never logged.

## 8. Measurement & Acceptance Approach

- Every batch gate runs the full deterministic acceptance suite + Jev shadow comparison:
  - "Determinism gate": with Jev disabled/unavailable, output is byte-identical to today's deterministic decision.
  - "Shadow parity audit": N observed cases; where Jev and deterministic disagree, deterministic wins and the divergence is logged.
  - "Availability gate": Jev outage/budget-exhaust path returns deterministic result with correct `source` label.
- CI additions: mock-Jev transport for hermetic tests; opt-in real-Jev integration job.

## 9. Scope of the Transformation (Phase 0)

This phase PRODUCES NO CODE. Deliverables only:
`MASTER_PLAN.md`, `CURRENT_STATE.md`, `ARCHITECTURE.md`, `DECISION_INVENTORY.md`,
`JEV_FEASIBILITY_REPORT.md`, `MIGRATION_MATRIX.md`, `TEST_AND_ACCEPTANCE_GATES.md`,
`RISKS_AND_OPEN_QUESTIONS.md`, `PHASE_0_AUDIT_REPORT.md`.
No migration is performed. No commits or pushes are made during Phase 0.