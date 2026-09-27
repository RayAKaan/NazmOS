# PHASE 2 — BATCH 1 SURFACE VERIFICATION EVIDENCE

- Date: 2026-09-23
- Repo root: `H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED`
- Branch: `phase1-core-infra-replacements` · HEAD: `6078008`
- Purpose: verify the Batch 1 candidate surfaces exist in code and hold passing
  deterministic tests BEFORE finalizing batch membership (exactly 3 per batch).

## 1. Batch 1 roster (per MIGRATION_MATRIX.md §1 / MASTER_PLAN.md) [V]
| # | Surface | Code owner (deterministic) | Shape |
|---|---------|---------------------------|-------|
| 1 | `recovery.rank` | `app/intelligence/agents/recovery_agent.py::propose` (SQL ORDER BY severity × impact, lines 56–58) + `app/services/prioritization.py::top_problems` (deterministic priority formula) | Choice over rank buckets |
| 2 | `recovery.action_type` | `app/orchestration/contracts.py::CANONICAL_ACTION_TYPES` + `app/services/outcome_learning.py::learning_adjusted_action` + `app/services/action_registry.py` (can_execute/filter_action) | Choice over canonical actions |
| 3 | `audit.root_cause_bucket` | `app/services/root_cause.py::investigate_root_cause` + `ROOT_CAUSE_STRATEGIES` + `HYPOTHESIS_GENERATORS` | Choice over root-cause taxonomy |

`inventory.stockout_tier` is verified to be a **Batch 2 score surface** (no named
tier symbol exists today — only `stockout_risk` finding category,
`stockout_financials`, `po_classify_status`); matrix §2 already defers it with a
documented pre-req (create a named tier fed by classify_status). [V]

## 2. Verification result [H]
Ran the deterministic test set covering all three surfaces + learning/recovery
loops:

```
python -m pytest tests/test_phase13_prioritization.py tests/test_phase12_closed_loop.py \
  tests/test_phase10_loop.py tests/test_phase7_loop.py tests/test_phase6_loop.py \
  tests/test_business_decision_loop_v1.py tests/test_phase1_decision_safety_comprehensive.py -q
```
Before fixes: **91 passed, 4 failed**. After fixes: **95 passed**. [H]
Related outcome-feedback/learning regressions also green: **23 passed**
(`test_learning_advanced`, `test_learning_engine`, `test_phase5_learning_loop`). [H]
`python -m compileall -q app tests` → exit 0. [H]
Evidence: `results/phase2_b1_surface_verification.txt`.

## 3. Defects found & fixed during verification (all non-destructive code fixes)
1. `app/services/root_cause.py:53` — `NameError: name 'Decimal' is not defined`
   in `_stockout_hypotheses` → added `from decimal import Decimal`. [FIXED]
2. `app/services/root_cause.py:53` — after the import fix surfaced a second bug:
   `str(raw_velocity) * 30` string-multiplied the velocity text (→
   `decimal.InvalidOperation: ConversionSyntax`); corrected to
   `str(raw_velocity * 30)`. [FIXED]
3. `app/services/outcome_learning.py:266-353` — the OutcomeFeedback bridge in
   `record_unified_outcome` referenced an undefined `row` (NameError) and then
   shadowed the module-level `_json()` helper with `import json as _json`
   (`'module' object is not callable`), silently skipping the bridge. Fixed to
   read back the just-upserted `learned_outcomes` row (single write path) and
   removed the shadowing import. This is the §17 foundation bridge — the fix
   unblocks the phase 6/7 loop tests and the §17 outcome/business-state target.
   [FIXED]

## 4. Batch 1 membership verdict
**CONFIRMED — Batch 1 surface roster verified, deterministic tests green,
eligible to begin migration via the canonical controller.**