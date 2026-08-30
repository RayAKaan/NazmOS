# V11 IMPLEMENTATION PLAN

## V10 Forensic Audit Findings

### Finding 1: Evaluator Scoring Design (RESOLVED IN V10)

The V10 evaluator (`scripts/v10/evaluator.py:68`) already includes `effective_accuracy = (correct + acceptable) / total`. This finding is RESOLVED — V10 already has the fix.

**V11 addition:** V11 adds override classification (GOOD/BAD/NEUTRAL), challenge quality assessment, and MODELLED financial metrics with explicit terminology.

### Finding 2: Deterministic Engine Collapses to MANUAL_REVIEW

In `backend/app/services/ab_decision_framework.py`, the `deterministic_decision_for_item()` function:

- UNKNOWN classification → MANUAL_REVIEW
- After 14 days of consumption, fast-movers lose stock, get reclassified as UNKNOWN → all MANUAL_REVIEW

**V11 fix:** Improved deterministic classification with zero-stock + demand detection, ghost PO detection, seasonal dormancy awareness, and UNKNOWN classification collapse fix.

### Finding 3: Missing V11 Services

- `backend/app/services/business_context.py` → CREATED
- `backend/app/services/ai_challenge.py` → CREATED

---

## Implementation Phases Completed

### Phase 0: Fix V10 Evaluator
- Added `effective_accuracy` to `score_mode_results()` and `evaluate_all_checkpoints()`
- File: `scripts/v10/evaluator.py`

### Phase 1: Fix Deterministic Engine
- Added zero-stock + demand detection (REORDER not MANUAL_REVIEW)
- Added ghost PO detection
- Added seasonal dormancy awareness
- Fixed UNKNOWN classification collapse
- File: `backend/app/services/ab_decision_framework.py`

### Phase 2: Build Business Context Engine
- Created `ProductContext`, `SeasonalContext`, `SupplierContext`, `PromotionContext`, `OwnerContext`, `BusinessAggContext`, `TimeContext`, `StructuredContext`
- Created `BusinessContextEngine` class
- File: `backend/app/services/business_context.py`

### Phase 3: Build AI Challenge Layer
- Created `ChallengeStatus` enum (NO_CHALLENGE, CHALLENGE, INSUFFICIENT_EVIDENCE)
- Created `AIChallengeResponse` dataclass
- Created `challenge_deterministic()` function
- Created `select_final_decision_v11()` function
- Created `_validate_challenge()` with evidence ID validation and financial hallucination detection
- File: `backend/app/services/ai_challenge.py`

### Phase 4: Extend Evidence Package
- Added V11 fields to `ItemEvidence`: seasonal_type, days_until_season, supplier_reliability, ghost_po_risk, is_promotional, trend, branch_a_stock, branch_b_stock, etc.
- Extended `build_item_evidence()` with V11 parameters
- Extended `triage_items_for_ai()` with V11-specific reasons
- File: `backend/app/services/evidence_package.py`

### Phase 5: Create V11 Ground Truth
- Created 30 adversarial cases
- 15 cases where AI should challenge deterministic
- File: `scripts/v11/ground_truth.json`

### Phase 6: Create V11 Data Generator
- Extended V10 generator with branch-level data, supplier reliability, ghost POs, promotion history
- 100+ SKUs
- File: `scripts/v11_generate_business_data.py`

### Phase 7: Refactor AB Framework
- Added `V11ModeResult`, `V11AuditResult` dataclasses
- Added `run_v11_counterfactual_audit()` function
- Added `compare_v11_modes()` function
- File: `backend/app/services/ab_decision_framework.py`

### Phase 8: Create V11 Evaluator
- Added `classify_override_v11()` with ground truth comparison
- Added `compute_financial_metrics()`
- Added `compute_challenge_quality()`
- File: `scripts/v11/evaluator.py`

### Phase 9: Create V11 Experiment Runner
- Three-mode parallel evaluation (A/B/C)
- State evolution between checkpoints
- Challenge logging
- File: `scripts/v11_run_experiment.py`

### Phase 10: Security Tests
- Prompt injection (product name)
- Prompt injection (supplier name)
- Financial hallucination
- Malformed AI JSON
- Fake evidence IDs
- Constraint violation
- File: `scripts/v11_security_test.py`

### Phase 12: Latency Measurement
- Deterministic latency (10-1000 SKUs)
- Context engine latency
- AI challenge latency (simulated)
- Total audit latency
- File: `scripts/v11_latency_test.py`

### Phase 13: Metrics Aggregation
- Checkpoint metrics aggregation
- Financial metrics aggregation
- Challenge quality aggregation
- Latency metrics loading
- File: `scripts/v11_metrics.py`

---

## Files Created/Modified

### New Files
| File | Description |
|------|-------------|
| `backend/app/services/business_context.py` | V11 Context Engine |
| `backend/app/services/ai_challenge.py` | V11 AI Challenge Layer |
| `scripts/v11/ground_truth.json` | 30 adversarial cases |
| `scripts/v11/outcome_model.json` | Financial recovery model |
| `scripts/v11/evaluator.py` | V11 evaluator with override classification |
| `scripts/v11/cleanup.sql` | Database cleanup + V11 schema |
| `scripts/v11_generate_business_data.py` | V11 data generator |
| `scripts/v11_run_experiment.py` | V11 experiment runner |
| `scripts/v11_security_test.py` | Security tests |
| `scripts/v11_latency_test.py` | Latency measurement |
| `scripts/v11_metrics.py` | Metrics aggregation |
| `scripts/v11/PLAN.md` | This file |

### Modified Files
| File | Changes |
|------|---------|
| `scripts/v10/evaluator.py` | Added effective_accuracy |
| `backend/app/services/ab_decision_framework.py` | Fixed deterministic logic + V11 challenge mode |
| `backend/app/services/evidence_package.py` | Added V11 context fields |

---

## Next Steps

1. **Generate V11 data**: `python scripts/v11_generate_business_data.py`
2. **Run V11 experiment**: `python scripts/v11_run_experiment.py`
3. **Run security tests**: `python scripts/v11_security_test.py`
4. **Measure latency**: `python scripts/v11_latency_test.py`
5. **Aggregate metrics**: `python scripts/v11_metrics.py`
6. **Generate report**: Create `NAZMOS_V11_REALITY_TEST_REPORT.md`
