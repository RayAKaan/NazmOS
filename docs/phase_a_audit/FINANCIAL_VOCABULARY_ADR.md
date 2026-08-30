# ADR: Financial Vocabulary Trace & Normalization

**Status**: ACCEPTED  
**Date**: 2026-08-29  
**Author**: Phase A Audit

---

## 1. Decision

The financial vocabulary across the codebase has **semantic drift** between modules. A normalization layer is needed to enforce canonical field names and formulas.

---

## 2. Canonical Vocabulary (from `evidence_package.build_item_evidence`)

| Canonical Field | Formula | Source |
|----------------|---------|--------|
| `inventory_value_sar` | `stock * cost` | `evidence_package.py:170` |
| `capital_at_risk_sar` | `inventory_value_sar` (for DEAD/SLOW) | `evidence_package.py:184` |
| `revenue_at_risk_sar` | `stock * sell` (if velocity > 0 else 0) | `evidence_package.py:185` |
| `gross_profit_at_risk_sar` | `revenue_at_risk_sar - inventory_value_sar` | `evidence_package.py:186` |
| `recoverable_low_sar` | `0` (conservative) | `evidence_package.py:218` |
| `recoverable_high_sar` | `min(inventory_value, stock * sell)` | `evidence_package.py:219` |
| `expected_recovery_sar` | `None` (filled by AI/calibration) | `evidence_package.py:220` |

**All monetary fields use `_sar` suffix and 2-decimal rounding.**

---

## 3. Identified Drift Points

| Module | Drift | Impact |
|--------|-------|--------|
| `money_audit_service.py` | Uses `recoverable_value_low_sar` / `recoverable_value_high_sar` in action dicts (lines 378-379, 550-551) | Breaks key-name compatibility with `ItemEvidence` |
| `money_audit_service.py` | DB column `expected_recovery_sar_v2` (line 289) | Dual naming for same concept |
| `audit_report_service.py` | SELECT uses `recoverable_value_low_sar` / `recoverable_value_high_sar` (line 33) | DB schema drift |
| `guest_audit_service.py` | Uses `recoverable_value_low_sar` / `recoverable_value_high_sar` (lines 202-203, 264-265) | Same drift |
| `recovery_intelligence.FinancialEstimate` | Fields: `recoverable_low`, `recoverable_high`, `expected_recovery` (no `_sar` suffix) | Source of drift; `.json()` preserves names |
| `business_context.py:357` | Maps `total_recoverable_sar = business.total_recoverable_high_sar` | Loses `_high` distinction |
| `closed_loop_experiment.py:461` | Computes `recoverable_high_sar = stock * sell * 1.5` (different formula) | Overestimates vs canonical `min(inventory_value, stock*sell)` |
| `ai_response_validator.py` | Collects SAR values using canonical `_sar` names (lines 484-490) | Validator expects canonical names |

---

## 4. Data Flow Trace

```
evidence_package.build_item_evidence()
    → ItemEvidence (canonical fields)
    → money_audit_service.run_money_audit()
        → recovery_intelligence.estimate_recovery() → FinancialEstimate
        → Action dicts: renames recoverable_low → recoverable_value_low_sar
    → audit_engine.process_audit()
        → Carries expected_recovery_sar through evidence dict
    → audit_report_service.get_latest_audit_summary()
        → SELECT recoverable_value_low_sar (DB column name)
    → BusinessContextEngine.build_business_context()
        → Maps total_recoverable_high_sar → total_recoverable_sar (loss of _high)
    → ab_decision_framework.run_counterfactual_audit()
        → Passes ItemEvidence fields directly (canonical)
```

---

## 5. Normalization Requirements

### 5.1 Field Name Unification
| Target Canonical | Current Aliases | Action |
|------------------|----------------|--------|
| `recoverable_low_sar` | `recoverable_low`, `recoverable_value_low_sar` | Add `@property` aliases or migration |
| `recoverable_high_sar` | `recoverable_high`, `recoverable_value_high_sar` | Same |
| `expected_recovery_sar` | `expected_recovery`, `expected_recovery_sar_v2` | Same |
| `capital_at_risk_sar` | `capital_at_risk` | Same |

### 5.2 Formula Unification
- `closed_loop_experiment.py:461` → use `min(inventory_value, stock * sell)` 
- `recovery_intelligence` already uses `min(inventory_value, gross_proceeds)` — consistent ✓

### 5.3 DB Schema
- `money_audit_actions.expected_recovery_sar_v2` → rename to `expected_recovery_sar`
- `money_audit_actions.recoverable_value_low_sar` → rename to `recoverable_low_sar`
- `money_audit_actions.recoverable_value_high_sar` → rename to `recoverable_high_sar`

---

## 6. Validation Guard

`ai_response_validator._collect_evidence_sar_values()` (lines 484-490) expects canonical names. This is the enforcement point: if a module produces non-canonical keys, the validator will not recognize them, potentially causing false hallucination flags.

---

## 7. Recommendation

1. **Immediate**: Add property aliases to `FinancialEstimate` for `_sar` names (backward compatible)
2. **Phase A**: Create `financial_vocabulary.py` with canonical constants + normalization helpers
3. **Phase B**: Migrate DB columns (requires migration script)
4. **Ongoing**: Use `financial_vocabulary.canonical_keys` in all new code

---

## 8. Verification

- `ai_response_validator._verify_financial_claims` uses canonical keys → will pass with canonical data
- Tests in `test_v8_comprehensive.py` use `ItemEvidence` canonical fields → pass
- No tests currently assert non-canonical field names directly