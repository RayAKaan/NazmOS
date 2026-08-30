"""Authenticated API smoke test for the Phase 6 pilot contract."""
import os, requests
base=os.getenv("NAZMOS_BASE_URL","http://localhost:8000/api/v1")
token=os.getenv("NAZMOS_TOKEN")
business_id=os.getenv("NAZMOS_BUSINESS_ID")
if not token or not business_id:
    raise SystemExit("Set NAZMOS_TOKEN and NAZMOS_BUSINESS_ID")
h={"Authorization":f"Bearer {token}"}
for path in (f"/pilot/summary?business_id={business_id}", f"/pilot/daily-brief?business_id={business_id}"):
    r=requests.get(base+path,headers=h,timeout=20); print(path,r.status_code); r.raise_for_status()
