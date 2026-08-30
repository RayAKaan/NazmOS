import pandas as pd
import sys
sys.path.insert(0, "/app")
from app.services.data_normalizer import normalize_dataframe

m = {"item_name":"item_name","item_sku":"item_sku","quantity":"quantity",
     "transaction_at":"transaction_at","unit_price":"unit_price","total_amount":"total_amount"}

def test(name, df, mapping):
    try:
        norm = normalize_dataframe(df, mapping, strict=True)
        rep = norm.attrs.get("data_quality_report", {})
        print(f"{name:<22} IMPORTED {len(norm)} rows rejected={rep.get('rejected')}")
        return "IMPORT"
    except Exception as e:
        print(f"{name:<22} REJECTED: {str(e)[:200]}")
        return "REJECT"

test("invalid_number", pd.DataFrame([{"item_name":"X","item_sku":"A","quantity":"abc","transaction_at":"2026-05-01","unit_price":"10","total_amount":"10"}]), m)
test("invalid_date", pd.DataFrame([{"item_name":"X","item_sku":"A","quantity":"5","transaction_at":"not-a-date","unit_price":"10","total_amount":"50"}]), m)
test("missing_name", pd.DataFrame([{"item_name":"","item_sku":"A","quantity":"5","transaction_at":"2026-05-01"}]), m)
mt = dict(m); mt["transaction_type"] = "transaction_type"
test("unknown_type", pd.DataFrame([{"item_name":"X","item_sku":"A","quantity":"5","transaction_at":"2026-05-01","transaction_type":"fraud_type","unit_price":"10","total_amount":"50"}]), mt)
test("no_window", pd.DataFrame([{"item_name":"X","item_sku":"A","note":"h"}]), {"item_name":"item_name","item_sku":"item_sku","note":"note"})
test("duplicate_rows", pd.DataFrame([{"item_name":"D","item_sku":"D1","quantity":"5","transaction_at":"2026-05-01"}]*2), m)
