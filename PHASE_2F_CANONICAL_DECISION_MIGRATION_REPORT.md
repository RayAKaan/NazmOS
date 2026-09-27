# PHASE 2F REPORT - CANONICAL TYPED DECISION MIGRATION (Batches 1-3)

Status: **GREEN** [V]

## Scope
- Migrate the 8 ranked Jev-scored surfaces onto canonical typed contracts
  through the single policy-checked choke point, exactly three per batch, each
  batch fully tested + accepted. Deterministic decision is ALWAYS final.

## Evidence
- Batch 1 (ACCEPTED): recovery.rank, recovery.action_type,
  audit.root_cause_bucket → `canonical_rank` / `canonical_action_type` /
  `canonical_root_cause`. [V]
- Batch 2 (MIGRATED 2 + DEFERRED 1): inventory.stockout_tier,
  inventory.anomaly_triage → `canonical_stockout_tier` /
  `canonical_anomaly_triage`; procurement.supplier_risk DEFERRED per §2 strict
  rule (no payment-history/cost-variance ground truth). [V]
- Batch 3 (MIGRATED 3): procurement.reorder_urgency,
  pricing.margin_erosion_risk, report.finding_priority →
  `canonical_reorder_urgency` / `canonical_margin_erosion` /
  `canonical_finding_priority` — wrapper bands `reorder_urgency_band()` /
  `margin_erosion_band()` / `finding_priority_token()` mirror the verified
  deterministic ladders/thresholds; dead code (`DEAD_STOCK_DAYS=45`, 
  procurement_agent reorder loop) explicitly NOT consulted. [V]
- All entry points preserve exact production signatures (one-line substitution
  per surface); contracts in `app/orchestration/contracts.py`; per-surface
  output gates `_validate_*`; capability registration in ai_policy.py. [V]

## Gate / verdict (MIGRATION_MATRIX §7, every surface)
| Gate | Result |
|---|---|
| Determinism | GREEN — byte-identical with Jev off; correct source_label |
| Shadow parity | GREEN — divergence logged & deterministic wins |
| Availability | GREEN — Jev down/budget-exhaust → fallback + audit |
| Governance/RLS | GREEN — DLP capsule; no business_id in capsule; autonomy_dial unchanged |
| Contract | GREEN — keys validated vs canonical frozensets; JEV_OUT_OF_CONTRACT on discard |
| CI | GREEN — 65 combined canonical green (284.49s) |

Cross-reference: `PHASE_2_B1_CANONICAL_CONTROLLER_EVIDENCE.md`,
`PHASE_2_B2_CANONICAL_MIGRATION_EVIDENCE.md`,
`PHASE_2_B3_CANONICAL_MIGRATION_EVIDENCE.md`, `MIGRATION_MATRIX.md` §§1-3.