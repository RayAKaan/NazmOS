# DECISION_INVENTORY.md

**Every decision surface in NazmOS, mapped to the 14 strategic capabilities, with deterministic-vs-Jev suitability.**

Audit basis: the 8 domain agents under `backend/app/intelligence/agents/`, the routers/services that consume them, and the deterministic decision funnel `ab_decision_framework.deterministic_decision_for_item`. Evidence labels: [V] verified, [I] inferred, [NP] not present.

## 0. Key structural facts (verified)

- **No runtime path calls an LLM to make a business decision.** All 14 capabilities are algorithmic/heuristic today. LLM usage is limited to advisory reasons/challenges and chat (`ai_reasoning.py`, `ai_challenge.py`, chat router). [V]
- The **single canonical deterministic decision function** is `ab_decision_framework.deterministic_decision_for_item` (`app/services/ab_decision_framework.py:91`). It is the compelled insertion point for Jev shadow evaluation. [V]
- Some capability labels in the plan do NOT exist as code symbols (`inventory.stockout_tier`) or are orphans (`inventory.anomaly_triage`) — see per-item notes. Mappings below are to the real, verifiable code.

## 1. Capability-by-capability inventory

| # | Strategic capability | Code owner / function | Deterministic today? | Jev suitability (shadow) | Notes & evidence |
|---|---|---|---|---|---|
| A | `recovery.rank` | `intelligence/agents/recovery_agent.py` — sala ranking of recovery candidates (`recovery_match_service`) | YES [V] | **HIGH** — Choice over rank buckets | Rank is a comparison of deterministic values; Jev Choice on ordinal buckets is a clean shadow. |
| B | `recovery.action_type` | recovery agent + `orchestration/contracts.py` `CANONICAL_ACTION_TYPES` (line 17-24) [V] | YES [V] | **HIGH** — Choice over the canonical action-type set | Wrapper returns only contract-set members; Jev Choice key must equal `CANONICAL_ACTION_TYPES`. |
| C | `audit.root_cause_bucket` | `intelligence/agents/compliance_agent.py` / money-audit root-cause path (`app/services/root_cause.py`) | YES [V] | **HIGH** — Choice over root-cause taxonomy | `root_cause.py` computes buckets; deterministic bucket remains authoritative. |
| D | `inventory.stockout_tier` | **NO direct symbol** — behavior via `classify_status`/urgency ints (`inventory_agent.py`, `analytics_service`) | YES [V] | **MEDIUM** — Score over urgency ladder, must mirror deterministic `classify_status` | Plan label ≠ code symbol. Jev Score must be validated against deterministic tiers; if mismatch → deterministic. |
| E | `inventory.anomaly_triage` | **ORPHANED** — detector emits anomalies; nothing persists to `findings`; no consumer/ground-truth table [V] | PARTIAL [V] | **MEDIUM (needs ground truth first)** | No downstream consumer → no verified outcome to learn from. Fix persistence before batching. |
| F | `procurement.reorder_urgency` | `procurement_agent.py` (reorder decisions, `reorder_urgency`) | YES [V] | **HIGH** — Score urgency ladder | Watch dead-stock 45-vs-30 inconsistency feeding urgency. |
| G | `inventory.anomaly_type` | `inventory_agent.py` / anomaly detection paths | YES [V] | **LOW** | Geared to deterministic rules; low value. |
| H | `pricing.margin_erosion_risk` | `pricing_agent.py`, `margin_agent.py`, `money_audit_service` margin analysis | YES [V] | **MEDIUM** — Score over erosion rubric | Needs a deterministic ground-truth target (e.g. `gross_margin_pct` threshold) to validate against; without it, calibration is unverifiable. |
| I | `report.finding_priority` | findings creation (`audit_engine`/`report`), severity/priority canonical | YES [V] | **MEDIUM-HIGH** — Choice over severity tiers | Tie Jev output to the findings severity contract; otherwise only advisory. |
| J | `pricing.owner_band_eligibility` | owner bandwidth gating (pricing agent / business rules) | YES [V] | **UNSUITABLE** [V] | Band/eligibility is a deterministic access rule (governance). Do NOT delegate. |
| K | `governance.shariah_review_triage` | compliance_agent.py Shariah review/reasoning | YES [V] | **UNSUITABLE** [V] | Religious compliance triage must never be delegated to a model whose lifecycle can change behavior. Deterministic rubric only. |
| L | `procurement.moq_risk` | procurement agent MOQ logic | YES [V] | **DEFERRED** | Calibration hard without ground truth; batch-3 position kept per plan. |
| M | `finance.cash_action_priority` | finance_agent.py cash-action priority | YES [V] | **DEFERRED** | Cash priority = money-critical; deterministic-first per master plan. |
| N | `approval.routing_priority` / `approval.urgency_score` | approval automation + autonomy dial (`precheck.py:18`, `autonomy_service.py`) | YES [V] | **DEFERRED** | Approval routing belongs to governance dial semantics (0/1–94/95–100); documented only. |

## 2. Cross-cutting observations

- **Dead-stock threshold divergence** feeding several of the above: `DEAD_STOCK_DAYS = 45` (`audit_core.py:28`, `money_audit_service.py:20`) vs 30-day scans (`audit_engine.py:127`, `goal_service.py:79`, analytics 30-day default). Any Jev prompt/Score ladder built on dead-stock must state the window explicitly or go through the canonical rule (`analytics/contracts.py:75`: "< 1 unit sold in window with stock"). [V]
- **Velocity convergence is incomplete** (see MIGRATION_MATRIX / CURRENT_STATE): inline `/30` sites remain (`audit_engine.py:173`, `inventory_orchestrator.py:46`, `nazm_planner.py:486`, `intelligence_api.py:233`). Jev migration of any velocity-derived surface must happen AFTER the canonical function is fully rolled out. [V]
- **Anomaly triage has no persistence** — it must be fixed (persist to `findings`/evidence) before any Jev triage batch, or there is no ground truth to score against. [V]

## 3. Recommended batch assignments (aligned to Master Plan §4)

- **Batch 1**: A `recovery.rank` (Choice), B `recovery.action_type` (Choice), C `audit.root_cause_bucket` (Choice).
- **Batch 2**: D `inventory.stockout_tier` (Score, deterministic-aligned), E `inventory.anomaly_triage` (Choice+Score, after persistence fix), F `procurement.reorder_urgency` (Score).
- **Batch 3**: G `inventory.anomaly_type` (low value; require explicit ground truth), H `pricing.margin_erosion_risk` (Score with `gross_margin_pct` target), I `report.finding_priority` (Choice over severity contract).
- **Deferred/never**: J, K (unsuitable), L, M, N (deferred per governance & money-criticality rules).

## 4. Interface contract for Jev integration

- Every migrated surface exposes a typed question (Choice/Score/Noul) PLUS the deterministic result. The deterministic answer is always present in the response; Jev adds `evidence` and never overrides.
- Confidence thresholds require a labelled sample from deterministic ground truth before any threshold is trusted (Jev returns calibrated probabilities — not guarantees). Dead band in the middle where nothing acts automatically.