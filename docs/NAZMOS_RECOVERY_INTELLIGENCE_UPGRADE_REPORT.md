# NazmOS Recovery Intelligence Upgrade

## Production decision

**NOT READY**

The financial model and ingestion safety have been materially upgraded, but the supplied execution environment does not contain the production database/runtime dependencies needed to prove a full UI/API audit run, timing promise, WhatsApp loop, or five-business end-to-end outcome test. It would be dishonest to label this build Pilot Ready or Production Ready without that evidence.

## A. Implementation Summary

### Financial model

Added a v2 financial model that separates:

- inventory value
- capital at risk
- revenue at risk
- gross-profit at risk
- recoverable value range
- expected recovery
- recovery confidence

The old `money_at_risk_sar` field remains only for backward compatibility. New audit summaries and the merchant UI use the separated measures.

### Recovery intelligence

Added `backend/app/services/recovery_intelligence.py` with deterministic, evidence-first logic:

- conservative inventory classification
- seasonal/unknown handling
- evidence-bounded recovery ranges
- observed-outcome calibration
- stockout revenue/profit risk
- transparent action simulation

Arbitrary fixed recovery percentages were removed from the Money Audit path.

When observed recovery outcomes do not exist, `expected_recovery_sar` is intentionally `null` rather than guessed.

### Outcome calibration

Completed Money Audit actions now support:

- expected recovery
- observed completed value
- measurement window
- prediction error

Future completed actions can therefore calibrate the recovery estimate using observed action outcomes.

### Explainability

Each Money Audit action now persists an evidence payload containing source facts such as:

- SKU
- item name
- stock
- cost
- selling price
- recent velocity
- prior-period velocity
- last-sale age
- inventory age when available
- days of supply
- supplier information when actually available
- classification

### Action simulation

Added:

`POST /api/v1/money-audit/actions/{action_id}/simulate`

The simulator explicitly labels results as estimates and only uses observed historical prices or explicitly supplied branch demand. It does not invent transfer demand or guarantee recovery.

### Business-specific behavior

Cafe and restaurant audits now explicitly identify themselves as limited product-level analysis when recipe/ingredient data is not being used. The system no longer implicitly claims full food-cost intelligence from generic inventory data.

## B. Financial Model — Before vs After

| Before | After |
|---|---|
| One `money_at_risk` headline | Separate economic measures |
| Dead stock × 35% | Evidence-bounded recovery range |
| Overstock × 30% | No arbitrary recovery percentage |
| Stockout = 7 days sales | Revenue/profit risk separated from recovery |
| Margin leakage treated like recoverable money | Gross-profit opportunity explicitly separated |
| Expected recovery always numeric | Expected recovery withheld without evidence |
| Confidence mostly data-quality based | Recovery confidence explicitly represented |
| No calibration for Money Audit actions | Completed outcomes can calibrate future estimates |

## C. Data Integrity

### Fixed

- Invalid dates are identified before coercion.
- Invalid numeric values are identified before coercion.
- Negative quantities require an explicit transaction classification.
- Returns/refunds are normalized as positive units with explicit transaction types and negative financial amounts.
- Duplicate source rows are reported.
- Duplicate SKUs mapping to multiple product names are reported as warnings.
- Malformed CSV rows are no longer silently skipped.
- CSVs above `MAX_ROWS` are rejected.
- Excel files above `MAX_ROWS` are rejected.
- Upload reconciliation now stores received, rejected and imported counts.
- Rejected-row details are persisted on the upload record.
- Data-quality score is affected by rejected rows and sales-history coverage.

### Transaction classifications

Supported explicitly:

- sale
- return
- refund
- waste
- adjustment
- transfer

Sales velocity calculations only treat sale/return/refund as demand-bearing transactions.

### Remaining ingestion limitation

The complete runtime upload → ETL → PostgreSQL reconciliation path could not be executed in the supplied environment because required runtime dependencies/database infrastructure are unavailable.

## D. Recovery Intelligence

The recovery layer now distinguishes:

**Detected problem**

A product appears operationally problematic.

**Financial impact**

The economic exposure associated with that problem.

**Recoverable opportunity**

An evidence-bounded range that could plausibly be changed through an action.

**Expected recovery**

Only populated when observed completed outcomes provide calibration evidence.

**Actual recovery**

Only populated from owner-completed action outcomes.

This prevents projected revenue from being presented as recovered cash.

## E. Explainability

Major actions now include source evidence. For example, a slow-inventory action can expose:

- current stock
- cost basis
- sell price
- inventory value
- recent 30-day quantity
- preceding 30-day quantity
- days since last sale
- inventory age
- classification

Stockout actions expose:

- current stock
- daily velocity
- days of supply
- supplier lead time when explicitly configured
- safety stock when available
- supplier name when available
- supplier minimum order value when available

If supplier lead time is unavailable, the recommendation confidence is reduced rather than inventing a lead time.

## F. Tests

Added **10 adversarial/regression tests** across three areas:

### Recovery intelligence

- no fabricated expected recovery
- evidence-bounded recovery range
- seasonal/uncertain classification
- stockout revenue/profit separation
- calibration from observed outcomes
- action-simulation labeling

### Data integrity

- invalid date rejection
- negative quantity rejection without explicit type
- explicit return normalization
- duplicate-row detection

### Reality-test protocol

- five-business corpus validation
- hidden-ground-truth separation
- corruption fixture validation

Also added the second Reality Test generator under:

`backend/tests/adversarial/generate_reality_test_v2.py`

The generated corpus contains five independent businesses, 120 days of sales history, inventory snapshots, a separate hidden ground truth, and a corruption fixture.

## G. Adversarial Results

### Static / isolated validation completed

- Backend Python compilation: **PASS**
- Recovery-intelligence isolated tests: **PASS**
- Second Reality Test corpus protocol: **PASS**
- Generated businesses: **5**
- Historical period: **120 days**
- Ground-truth rows: **25**
- Corruption cases: **15**

### Full product runtime

Not executed honestly because the environment lacks the required production runtime dependencies/database infrastructure.

Therefore these metrics are deliberately **not fabricated**:

- actual upload → Money Audit time
- actual API detection precision
- actual API recall
- actual WhatsApp completion rate
- actual recovery-range calibration accuracy
- actual five-business end-to-end financial outcome

### Second Reality Test status

**Protocol ready; live E2E pending runtime infrastructure.**

The merchant input files and hidden ground truth are physically separated in:

`backend/tests/adversarial/fixtures/reality_v2/`

The hidden file is not referenced by the audit implementation.

## H. Remaining Weaknesses

1. The current Money Audit does not yet have enough real completed outcomes to produce strong calibrated expected-recovery estimates for most new merchants.
2. Supplier MOQ is available only when explicitly represented in the existing supplier data model; quantity-based MOQ is not yet universally available.
3. Recipe/ingredient intelligence remains limited for cafes and restaurants without recipe data.
4. Seasonal inference is deliberately conservative and should not be treated as a full demand-forecasting system.
5. Action simulation is transparent but still scenario-based; it is not a guarantee of execution or recovery.
6. The actual 1–2 minute promise remains unverified in this environment.
7. The complete continuous loop still needs production outcome data before it can demonstrate learning quality.

## I. Production Readiness

### NOT READY

The upgrade removes several serious financial-trust failures, especially the conflation of revenue risk with recoverable cash and silent ingestion loss.

However, production readiness requires the next runtime test to demonstrate:

`Upload → Reconcile → Audit → Approve → Execute → Measure → Calibrate`

against real database-backed execution.

## J. Next Three Priorities

### 1. Run the full five-business Reality Test on production-like infrastructure

Provision PostgreSQL, Redis and the required Python dependencies. Run the actual UI/API workflow and measure upload-to-audit latency, detection precision/recall, recommendation accuracy and end-to-end money outcomes.

### 2. Build the first real recovery calibration dataset

Capture completed action outcomes and calculate prediction error by action type, vertical and confidence tier. Do not add ML until enough transparent observations exist.

### 3. Strengthen vertical-specific context

Prioritize supplier lead time/MOQ and seasonal demand for grocery, then recipe/ingredient/wastage data for cafes and restaurants. Do not broaden autonomous claims before the required data exists.
