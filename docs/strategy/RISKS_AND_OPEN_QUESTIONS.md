# RISKS_AND_OPEN_QUESTIONS.md

**Risks, open questions, and decisions required from the owner — surfaced by the Phase 0 reality audit.**
Evidence labels: [V] verified, [H] historical, [I] inferred, [U] unverified, [B] blocked.

## 1. Blockers (must resolve before any migration)

| # | Risk | Evidence | Impact |
|---|---|---|---|
| R1 | **The repo does not compile.** `intelligence_api.py` (working tree) + `test_analytics_health_score.py` (committed) break compileall and `app.main` import → whole test suite uncollectable; CI red. | [V] reproduced; details CURRENT_STATE.md §3 | Blocks Phase 1 gate, Phase 2+, everything. |
| R2 | **`docs/phase2b_final_report.md` = PARTIAL.** Velocity caller convergence incomplete (inline `/30` in `audit_engine.py:173`, `inventory_orchestrator.py:46`, `nazm_planner.py:486`, `intelligence_api.py:233`, `root_cause.py:38/110`, `evidence_package.py:188` synthetic-only). | [V] | Financial-velocity drift between surfaces; Jev Score prompts read inconsistent velocity. |
| R3 | **Phase 2C acceptance never executed; 2C-C not started.** 2C-A (contracts.py) + 2C-B (outcome_feedback_contract) committed. | [V] | Contract layer unverified in practice. |
| R4 | **Nazmos Temporal worker is not functional in the running stack** — container "Up" but logs show endless `dns error` gRPC poll retries ("Name or service not known"); Temporal container itself marked unhealthy despite port 7233 reachable. | [V] `docker ps` + `docker logs` | Any USE_TEMPORAL=true execution path (incl. the WhatsApp RLS gate) is unreliable operationally. Startup is fail-closed only for the ping check; worker not polling. |
| R5 | **Live chat/AI path bypasses the policy/budget/capsule gateway** — production routes go `intelligence_api` → `llm_orchestrator` (Groq/Gemini); `ai_gateway.reason` (kill-switch, budget, capsule, audit) has zero production callers. | [V] | Existing "AI safety" claims only apply to a dormant path; Jev must be deliberately routed (recommended: through the gateway) and the Groq/Gemini path documented as-is. |

## 2. High risks (design-governing)

| # | Risk | Evidence | Mitigation |
|---|---|---|---|
| R6 | **Jev confidence ≠ accuracy.** Schema-constrained but can pick wrong-valid option with high confidence; TypeSafe concedes "zero-hallucination" is not empirical. | [V] web research | Deterministic override mandatory; thresholds from labelled ground truth; dead band; risk_flags. |
| R7 | **Jev gives no rationale** → cannot satisfy the `reasoning` field of the output contract natively; audit/compliance limits in regulated workflows. | [V] | Keep deterministic reasoning as authoritative; Jev = evidence only. |
| R8 | **Early access / waitlisted account.** `TYPESAFE_API_KEY` may be unobtainable today; API moves fast. | [V] web research | Start account request now; Phase 2 behind config flag with mock-Jev transport in CI; use the local `jev-support-mvp` mock as dev substitute. |
| R9 | **Anomaly triage is orphaned** — detector emits; nothing persists to `findings`; no consumer; no ground truth for Score calibration. | [V] | Fix persistence (findings/evidence) before batching `inventory.anomaly_triage`; otherwise batch is untestable. |
| R10 | **Dead-stock window divergence (45 vs 30 days)** feeds stockout/urgency surfaces. | [V] `DEAD_STOCK_DAYS` 45 (`audit_core.py:28`,`money_audit_service.py:20`) vs 30-day scans (`audit_engine.py:127`,`goal_service.py:79`, analytics default) | Decide a single canonical window; encode in canonical rule; state window explicitly in Jev ladders. |

## 3. Medium risks (pragmatic)

- **Budget economics**: Jev input billed $0.042/MTok; cost scales with `state` size; output free. TypeSafe concedes pricing may be subsidised (sustainability unproven). [V] → Keep state small; banded DLP signals; cache repeated evaluations.
- **Question independence**: Jev answers are independent, no chaining; a multi-signal decision cannot be built by feeding one answer into another within one request. [V] → Compose a single fan-out request; keep cross-signal logic deterministic.
- **FEATURE_FLAGS**: only `agent_enabled` and `chat_enabled` are consumed by routers; many design-intent flags (agent_pricing, agent_cash, forecasting, anomaly_detection) exist as keys but are not enforced router-side. [V] → Jev gating should not depend on under-enforced flags; gate via `ai_policy` capability flags + budget instead.
- **`ExecutionRequest` lacks `autonomy_dial`** — autonomy lives on business model (`autonomy_dial_at_creation`). [V] → If Jev evidence is ever considered for dial adjustments, the contract channel must be added deliberately (2C revision) — deferred.
- **Admin cruft**: 79 untracked files, many operator `.ps1`/`.out` "align_temporal_*" tooling and stale `nazmos_test_ci*` DBs. [V] → Schedule repo hygiene after gates are green; don't commit tooling noise.

## 4. Open questions for the owner

1. **Gateway routing decision** — make `ai_gateway.reason` the production AI + Jev entry point (recommended: add `jev_systemone` capability alongside `opencode_brain`, route Jev through gateway; leave Groq/Gemini chat as-is) or keep Jev in a separate transport? (DECISION REQUIRED)
2. **Jev account status**: key availability / team join to TypeSafe early-access? Start now — Phase 2 entry condition.
3. **Pin decision**: `jev-1.13.0` (recommended) vs `jev-latest`.
4. **Threshold ownership**: who labels the deterministic ground-truth samples to calibrate Choice/Score/Noul thresholds per surface?
5. **Dead-stock canonical window**: 30 vs 45 days — which becomes THE rule?
6. **Anomaly triage persistence**: approve building findings/evidence persistence as a Phase 1 follow-up so Batch 2 has ground truth?
7. **Worker/Temporal environment**: who restores the nazmos worker + Temporal container health (DNS/compose network) so the RLS gate and Temporal suite can run for real?
8. **`jev-support-mvp` role**: is it a sanctioned local mock for Phase 2 development, and should we contract-diff it against TypeSafe `/v1/systemone`?
9. **Scope of 2B completion**: confirm the 6 remaining inline `/30` sites are in Phase 1 scope (they must be, to make velocity deterministic across all Jev-scored surfaces).

## 5. Non-risks (stated to avoid over-correction)

- All 14 decision capabilities are **deterministic today**; Jev is purely additive. No production decision currently depends on a model. [V]
- DLP/privacy stack is well-built (`capsule`, `privacy_firewall`, `master_prompt` static + DLP-clean, no business_id in capsule). Jev integration slots into this. [V]
- Execution substrate (Temporal + dispatcher + idempotency) is the correct, already-guarded place; no change needed for Jev. [V]
- The `jev-support-mvp` local service is evidence of prior Jev-support thinking on this machine and is available for Phase 2 development. [V]