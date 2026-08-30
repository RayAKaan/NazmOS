# Merchant Scenarios

Deterministic synthetic test/demo fixtures (`backend/tests/fixtures/merchants.py`). **These
are NOT real Saudi merchant data** — they are controlled, deterministic datasets used to
validate audits, root-cause, strategy, learning, and reports.

## Available fixtures

- `seed_recurring_stockout_merchant` — high velocity + low stock + long lead time.
- `seed_margin_leakage_merchant` — supplier cost increased (+37.5%) vs price.
- `seed_successful_transfer_merchant` — base for strategy-history tests.

## Helpers

`seed_business`, `seed_category`, `seed_item`, `seed_inventory`, `seed_transactions`,
`seed_supplier`, `seed_supplier_price` — deterministic, UUID-isolated, tenant-scoped.

Every fixture produces internally-consistent relationships (business → category → item →
inventory → transactions → supplier → supplier_price), so audits/root-cause/strategy operate
on realistic structure without any fabricated external market data.
