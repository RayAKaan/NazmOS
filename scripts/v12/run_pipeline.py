"""V12 AI-OFF Reality Test - Phase 6/8 pipeline driver.

Bootstraps a FRESH owner + business ("Al Noor Superstore", supermart), uploads
the generated inventory + sales CSVs through the REAL API+ETL+Celery pipeline,
waits for import completion, then triggers a deterministic Money Audit.

Run (host):  python scripts/v12/run_pipeline.py
Requires backend up at http://localhost:8000 and the CSVs produced by
generate_v12_data.py.
"""
import json
import os
import sys
import time
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "sample_data", "v12")
EVID = os.path.join(ROOT, "results", "v12", "evidence")
os.makedirs(EVID, exist_ok=True)

BASE = "http://localhost:8000"
AUTH = "/api/v1/auth"
UPLOAD = "/api/v1/upload"
BIZ = "/api/v1/businesses"
MA = "/api/v1/money-audit"

EMAIL = "v12owner@nazmortestmail.com"
PASSWORD = "v12ownerPassw0rd"


def call(method, path, token=None, **kw):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    kw.setdefault("headers", {}).update(h)
    r = requests.request(method, BASE + path, timeout=120, **kw)
    try:
        body = r.json()
    except Exception:
        body = r.text
    return r.status_code, body


def register_or_login():
    code, b = call("POST", f"{AUTH}/register", json={
        "email": EMAIL, "password": PASSWORD, "full_name": "V12 Owner"})
    if code == 201 or (code in (400, 409)):
        if (code in (400, 409)):
            return login()
        return b
    return b


def login():
    code, b = call("POST", f"{AUTH}/login", json={"email": EMAIL, "password": PASSWORD})
    return b


def bootstrap(token):
    code, b = call("POST", f"{BIZ}/bootstrap", token=token, json={
        "name": "Al Noor Superstore", "type": "supermart",
        "address": "Tahlia St", "city": "Riyadh", "contact_phone": "+966500000001"})
    return code, b


def upload_csv(token, business_id, path):
    fn = os.path.basename(path)
    with open(path, "rb") as fh:
        files = {"file": (fn, fh, "text/csv")}
        data = {"business_id": business_id}
        r = requests.post(BASE + UPLOAD + "/", headers={"Authorization": f"Bearer {token}"},
                          files=files, data=data, timeout=180)
    try:
        body = r.json()
    except Exception:
        body = r.text
    return r.status_code, body


def confirm_mapping(token, upload_id):
    # empty mapping -> SchemaDetector auto-detects canonical columns
    code, b = call("POST", f"{UPLOAD}/{upload_id}/map", token=token,
                   json={"business_id": None, "column_mapping": {}})
    return code, b


def wait_status(token, upload_id, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        code, b = call("GET", f"{UPLOAD}/status/{upload_id}", token=token)
        if code == 200 and isinstance(b, dict):
            st = b.get("status")
            if st in ("completed", "failed"):
                return b
        time.sleep(3)
    return {"status": "timeout"}


def main():
    reg = register_or_login()
    token = reg.get("access_token")
    if not token:
        print("NO TOKEN", reg); sys.exit(2)

    code, biz = bootstrap(token)
    print("bootstrap", code, "business_id=", biz.get("id") if isinstance(biz, dict) else biz)
    if isinstance(biz, dict):
        business_id = biz.get("id")
    else:
        business_id = None
    if not business_id:
        # fetch /me
        code, me = call("GET", f"{AUTH}/me", token=token)
        business_id = me.get("business_id")
        print("me.business_id =", business_id, "role=", me.get("role"))

    print("business:", business_id)

    # upload inventory snapshot
    inv_path = os.path.join(DATA, "inventory_snapshot.csv")
    code, u1 = upload_csv(token, business_id, inv_path)
    print("upload inventory", code, u1.get("upload_id") if isinstance(u1, dict) else u1)
    if isinstance(u1, dict) and u1.get("upload_id"):
        up1 = u1["upload_id"]
        code, m1 = confirm_mapping(token, up1)
        print("  map inventory", code)
        s1 = wait_status(token, up1)
        print("  status inventory:", s1.get("status"),
              "imported=", s1.get("row_count_imported"), "failed=", s1.get("row_count_failed"))

    # upload sales history
    sales_path = os.path.join(DATA, "sales_history.csv")
    code, u2 = upload_csv(token, business_id, sales_path)
    print("upload sales", code, u2.get("upload_id") if isinstance(u2, dict) else u2)
    if isinstance(u2, dict) and u2.get("upload_id"):
        up2 = u2["upload_id"]
        code, m2 = confirm_mapping(token, up2)
        print("  map sales", code)
        s2 = wait_status(token, up2)
        print("  status sales:", s2.get("status"),
              "imported=", s2.get("row_count_imported"), "failed=", s2.get("row_count_failed"))

    # generate money audit
    code, a1 = call("POST", f"{MA}/generate", token=token, json={"business_id": business_id})
    print("generate audit", code)
    out = {"json": a1}
    json.dump(out, open(os.path.join(EVID, "audit_summary.json"), "w", encoding="utf-8"),
              indent=2, ensure_ascii=False, default=str)

    s = a1.get("summary") if isinstance(a1, dict) else {}
    if isinstance(s, str):
        try:
            s = json.loads(s)
        except Exception:
            s = {}
    print("AUDIT SUMMARY:", json.dumps(s, default=str, indent=2)[:3000])
    print("audit_id:", a1.get("id") if isinstance(a1, dict) else None)


if __name__ == "__main__":
    main()
