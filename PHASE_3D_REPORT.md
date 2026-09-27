# PHASE_3D — Opportunity & Impact (`app/services/business_loop/opportunity.py`)

> Deterministic opportunities first; impact is a *range of expectation*, never a claim of recovered cash. MASTER_PLAN §9, §14.

## What was built

A rule-based opportunity engine over a business-state snapshot. It never invents thresholds — each rule references documented NazmOS thresholds (`audit_core` / action_registry) or caller-supplied overrides:

| Rule | Threshold (default) | Matches audit_core |
|---|---|---|
| EXCESS_INVENTORY | ≥30 days supply **and** ≥SAR 500 value | overstock condition [V] |
| STOCKOUT_RISK | <5 days supply with open demand | stockout tier [V] |
| MARGIN_EROSION | gross margin < 22% target | margin leakage [V] |
| INVENTORY_ANOMALY | review candidate (anomaly triage reuse) | anomaly triage [V] |

Every `Opportunity` binds: deterministic `opportunity_id` (content-addressed), `state_version`, `evidence_ids`, `rule_version`, and **impact kind = POTENTIAL** (an estimate, explicitly never EXPECTED/VERIFIED here). `reproducible_impact` asserts impact recomputes identically from inputs.

## Impact honesty (§14)

- `impact_kind` distinct buckets: `potential`/`expected`/`approved`/`executed`/`verified`. The engine only ever produces POTENTIAL; verification (3I) is the sole path to VERIFIED.
- `expected_impact_sar` stays `None` unless supportable — estimate never equals verified.

## Gaps

G-3E (unified opportunity record) is closed at the loop level. Supplier-price-variance and full anomaly triage remain future candidates (`OpportunityType` enums reserved).