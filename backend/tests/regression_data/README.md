# Golden regression fixtures (Test-NazmOS)

Two pairs of CSV fixtures are used by the ETL regression harness.

## 1. `Test-NazmOS-Sales.csv` / `Test-NazmOS-Inventory.csv` (provided via chat)

**Provenance:** These files were supplied by the customer directly in the audit
session (answer to the golden-fixture question, 2026-09-07). They were pasted
verbatim into the conversation and extracted byte-for-byte by a subagent into
this directory. No values were reordered, normalized, or invented.

| File | Rows | Distinct days | Distinct SKUs | Distinct branches | Schema |
|---|---|---|---|---|---|
| `Test-NazmOS-Sales.csv` | 500 | 50 (2026-07-20 → 2026-09-07) | 18 (SKU-1001..1020 minus 1007,1018) | 5 | `business_id,transaction_id,transaction_date,sku,product_name,branch,transaction_type,quantity,unit_price_sar,unit_cost_sar` |
| `Test-NazmOS-Inventory.csv` | 100 | — | 20 (SKU-1001..1020) | 5 (`LOC-RYD/JED/DMM/MED/KHB`) | `business_id,sku,product_name,location_id,warehouse,city,quantity_on_hand,unit_cost_sar,reorder_point,active` |

Real-file derived facts (authoritative for the harness against these files):
- Inventory value (Σ `quantity_on_hand × unit_cost_sar`, empty cost treated as
  0) = **SAR 72,363.60**; per location: RYD 15,326.10 · JED 11,993.50 ·
  DMM 22,591.15 · MED 8,098.20 · KHB 14,354.65.
- One inventory row has an intentionally empty `unit_cost_sar`; one has an
  intentionally empty `reorder_point`; one marks `active=false`.
- Sales span 50 distinct calendar days with no gaps; the sales file carries three
  `RETURN` transactions (negative quantity).

## 2. `Test-NazmOS-Canonical-Sales.csv` / `Test-NazmOS-Canonical-Inventory.csv` (synthesized)

**Provenance:** The original audit accepted-family numbers — SALES = 91 rows over
6 distinct days, INVENTORY = 45 rows / 15 SKUs / 3 locations, inventory value
**SAR 28,892** — describe a *deterministic canonical merchant*. The source CSV
for that exact set was never delivered to the repo, so these two files are
generated deterministically by `scripts/build_golden_fixtures.py` to reproduce
those exact acceptance facts. They exist to make the "Dammam-only" regression
(structurally: 45 rows → 45 positions → 3 locations → 28,892) impossible to
regress silently, independent of the larger real-data fixture above.

To rebuild them:

```powershell
cd backend
python -m scripts.build_golden_fixtures
```

Derived facts (asserted by `tests/regression/test_golden_fixture_regression.py`):
- Canonical inventory = 45 rows, 15 SKUs, 3 locations (Riyadh Main, Jeddah
  Branch, Dammam Branch), 15 positions/location.
- Canonical inventory value = **SAR 28,892**; Dammam-only position value
  (the historical buggy projection) = **SAR 17,366**.
- Canonical sales = 91 rows, 6 distinct days (2026-08-04 → 2026-08-09),
  velocity exposes coverage (no day is ever extrapolated to 30).