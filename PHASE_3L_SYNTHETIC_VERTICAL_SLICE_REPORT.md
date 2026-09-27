# PHASE_3J — Synthetic Vertical Slice (`tests/test_phase3_synthetic_vertical_slice.py`)

> The smallest complete, synthetic, evidence-backed vertical slice, run end-to-end. MASTER_PLAN §19, §14, §22.

## What ran end-to-end (one cycle, all 21 stages)

```
synthetic POS observations ─► EvidenceStore (dedup, validation, lineage)
   ─► BusinessStateSnapshot (state_version, missing≠zero, lineage)
   ─► detect_opportunities (EXCESS_INVENTORY, SKU-EXC: 120×SAR20 @45d supply)
   ─► impact_calculation (POTENTIAL only)
   ─► action_candidates (recovery_match, transfer_inventory)
   ─► advisory: MOCKED Jev, source=mocked, provider=jev-mock, validated=True
        → contract-validated suggestion picks transfer_inventory
   ─► recommendation (version 1, material_hash, approved after approval_wait)
   ─► governance: APPROVAL_REQUIRED → simulated owner approval (labelled SYNTHETIC)
   ─► preflight → dry_run_execute → SyntheticReceipt (synthetic=True)
   ─► reconciliation: reported-recorded, allow_retry=False
   ─► verification: measurement authority (pre 2400 − post 400) → VERIFIED 2000.0
   ─► learning eligibility: TRUE (verified + observed + traceable)
   ─► cycle summary + next_cycle
```

## Authority boundaries asserted [V]

| Rule | Assertion |
|---|---|
| AI never authorizes | governance outcome is APPROVAL_REQUIRED, approval explicitly marked synthetic, `certified_by=deterministic-governance` |
| Estimates ≠ verified | impact stays POTENTIAL until the measurement authority produces `observed_impact_sar`; expected left None |
| Attribution exact | `advisory.source == mocked` (never labelled jev); provider recorded verbatim |
| Dry-run never real | `receipt.synthetic is True`, receipt note `SYNTHETIC - not a real merchant action` |
| No blind retry | reconciliation `allow_retry=False` reason `reported_recorded_await_verification` |
| Idempotent triggers | same `trigger_token` → same `cycle_id` (no duplicate cycle) |
| Successful no-op | no-opportunity cycle still completes with `learning_eligible=False` |
| Out-of-contract suggestion | recorded + dropped, never coerced; recommendation continues on deterministic path `advisory_validated=False` |

## Verification honesty

`observed_impact_sar` is produced by `_measurement_authority(pre_snapshot, post_snapshot)` which compares the pre-action state against the *post-action verification evidence*. The measurement is external reality (the POS/accounting pipeline in production); the loop does not invent the number. [V]

## Status

PASS — the complete synthetic vertical slice runs green end-to-end on the DB-free spine.