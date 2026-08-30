# Supplier-Price Sources

Status: **accurate as of Phase 11.** No purchase-cost webhooks are fabricated.

## Supported sources (real)

| Source | Path | Fields captured |
|---|---|---|
| ETL upload (CSV/XLSX with a `supplier` + `cost_price`/`unit_price` column) | `supplier_price_ingestion.ingest_from_etl_rows`, wired into `etl_pipeline` | supplier name, sku, unit price, currency, MOQ, effective date |
| Received purchase order | `supplier_price_ingestion.ingest_from_purchase_order` | supplier_id, item_id, unit_cost (from `items_json`) |

Every `SupplierPrice` row carries `source` and `effective_from`; `get_supplier_prices`
explicitly disclaims "not a market benchmark".

## Unsupported sources (do NOT fabricate)

- Foodics / Salla **purchase-cost webhooks** — the existing webhooks only emit *sales*
  orders (`pos.order.received`), never purchase costs.
- Synthetic supplier invoices, invented POS fields, merchant-to-merchant price aggregation.

## Future extension point

`supplier_price_ingestion.ingest_supplier_price()` is source-agnostic. A future
`purchase_document` source (accounting/ERP export, supplier invoice) only needs to call it
with: supplier name, SKU/barcode, unit price, currency, effective date, and (optional) MOQ.
