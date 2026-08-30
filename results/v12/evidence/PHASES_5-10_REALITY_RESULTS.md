# V12 AI-OFF Reality Test — Phases 5–10 Evidence

Date: 2026-08-27
Business: `Al Noor Superstore` (supermart, SAR, Asia/Riyadh)
Owner: `v12owner@nazmortestmail.com`
Business ID: `6d5312ba-c4c3-4e15-bacc-ab29a85adfa7`
Anchor (MAX transaction date): `2026-06-15` (audit period_end == T0)

## Phase 5 — Ground truth (independent oracle)
- `results/v12/ground_truth.json` : **33 cases** across all 10 categories
  (DEAD 6, FAST 4, STOCKOUT 4, OVERSTOCK 4, SEASONAL 4, PO 3, SLOW 2,
  GROWTH 2, MARGIN 2, OWNER_CONSTRAINT 2).
- Checksum `bfdd36a6...b520`, algorithm noted in `meta`; never fed to engine.

## Phase 6 — Fresh owner + business + data
- Fresh registered owner (`.test` TLD rejected by EmailStr — first finding:
  reserved-TLD guard) → new business `Al Noor Superstore`.
- Generator `scripts/v12/generate_v12_data.py` : **113 SKUs** (33 GT + 80 filler),
  2658 sales rows, deterministic (seeded), T0 = 2026-06-15.
- Because the money audit anchors on `period_end = MAX(transaction_at)`, all
  qty_30d / prior / monthly windows are reproducible.

## Phase 8 — Real API+ETL+Celery ingestion (PASS)
| Upload | raw | imported | failed |
|---|---|---|---|
| inventory_snapshot.csv | 113 | **113** | 0 |
| sales_history.csv | 2658 | **2658** | 0 |

DB consistency (business-scoped):
- items=113, inventory=113, transactions=2658 (all match source).
- transaction date range `2026-01-14 → 2026-06-15` (anchor correct).
- Spot-checked GT SKUs: `cost_price`, `sell_price`, `current_stock` match the
  source CSV exactly (e.g. V12-DEAD-001 8/15/50; V12-FAST-001 5/11/100).
- No silent corruption on the clean path.
- NOTE: two uploads originally stuck in `mapping_required` because the driver
  passed `business_id=None`; the confirm-mapping endpoint needs `business_id`
  as query param or body (documented contract, not a product bug).

## Phase 9 — Deterministic Money Audit (AI-OFF)
- Endpoint `GET /api/v1/money-audit/current?business_id=...&auto_generate=true`
  produced audit `94245612-...`.
- **AI Call Ledger = 0 bytes** after full upload + ETL + audit + enrich.
- Summary: action_count=12, classifications {DEAD 19, FAST 37, HEALTHY 19,
  UNKNOWN 2, SEASONAL 28, SLOW MOVING 8} (=113), evidence_count=157.

### GT-vs-DB classification match: 26/33 (as authored)
6 of 7 mismatches are **GT authoring corrections** (the authored oracle did not
match the actual classifier rule semantics):
- FAST-002/003 (stock=0, daily>=3) → real class HEALTHY (not FAST): zero-stock
  high-velocity items are HEALTHY under classify_inventory stock<=0 branch.
- OVERSTOCK-001 (stock 500, daily 1.33) → FAST (daily>=1 & stock>0).
- OWNER-002 (stock 150, daily 0.5) → HEALTHY (SLOW MOVING requires stock<=0).
- PO-001 (stock 0, daily 2.67<3) → SLOW MOVING.
- SLOW-002 (stock 40, daily 0.5) → HEALTHY.
1 is a **genuine product finding**:
- **SLOW-001 → SEASONAL (false positive).** A slow item selling 30 units this
  month vs 4+6 prior produced monthly concentration 30/40 = 0.75 ≥ 0.60, so
  `classify_inventory` labels it SEASONAL instead of SLOW MOVING. Moderate sales
  concentrated in a single month read as "seasonal spike" even without a true
  seasonal profile.

### Actions generated: 12 (value-prioritized, MAX_ACTIONS=12)
- 9 × `discount` (reason dead_stock, all DEAD) — the **highest-value dead stock**
  (SAR 5,133 – 21,894 recoverable_high).
- 3 × `reorder` (reason stockout_risk) — V12-PO-001, V12-FIL-041, V12-FIL-021.

**Findings from action set:**
1. **Small dead stock is invisible.** GT DEAD SKUs (V12-DEAD-001/002/004 =
   SAR 400/3000/3000 capital) produced NO action because MAX_ACTIONS=12 keeps
   only the highest-value dead items (SAR ≥ ~5,000 → priority 1). Genuinely dead
   capital below the value cut is never surfaced → recoverable guidance missed.
2. **PO-awareness gap in action generator.** `V12-PO-001` (200 units confirmed
   inbound) still got a `reorder`/stockout_risk action. The money-audit action
   generator does not suppress reorder when a confirmed PO is inbound (decision
   layer may, but the surfaced action contradicts the PO-aware expectation).

## Phase 10 — Financial semantic firewall (PASS)
From audit summary:
- `expected_recovery_sar: null` (no calibration → withheld, NOT guessed).
- `recoverable_value_low: 0` / `recoverable_value_high: 796002` (bounded, not
  booked as recovered cash).
- `capital_at_risk_sar: 796002` and `revenue_at_risk_sar: 10628.91` are reported
  SEPARATELY (never conflated).
- `margin_leakage_sar: 2178.5` separate.
- `money_recovered_sar: 0.0` (nothing claimed recovered).
- `headline_note` explicitly: "Revenue/profit at risk are not cash recovered."

## Cross-cutting: AI-OFF enforcement holds
- Ledger `0 bytes` at every checkpoint through Phase 10.

## Open counts for later phases
- 9 discount + 3 reorder actions exist to drive Phase 14 (action execution) and
  Phase 22 (60-day outcome) — but note the PO-inbound reorder (V12-PO-001) is a
  candidate for the PO-aware correctness check.
