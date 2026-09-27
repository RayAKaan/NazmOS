# PHASE_3F — Deterministic Impact & Candidate Selection (folded into 3D/3H)

> The vertical slice proves the deterministic path: impact is POTENTIAL until measured; action candidates come only from `action_registry`/[canonical action vocabulary](orchestration/contracts.py).

## What's covered here

- Impact accumulation across a cycle: `ImpactKind.POTENTIAL` set at `impact_calculation`; `expected` only when supportable; `executed`→`verified` strictly via 3H/3I receipts + measurement.
- Candidate action mapping: EXCESS_INVENTORY→{recovery_match, transfer_inventory}, STOCKOUT_RISK→{reorder, restock}, MARGIN_EROSION→{pricing_increase, margin_fix}, INVENTORY_ANOMALY→{review}. These mirror `ACTION_REGISTRY` keys (asserted in slice + `test_detect_excess_inventory` [V]).

## Boundaries

- No unregistered action is ever proposed (`detect_opportunities.eligible_actions` keys are registry-derived; governance DENIES anything else).
- Estimates and verified numbers are never co-mingled in one field: `potential_impact_sar` vs `expected/observed`.