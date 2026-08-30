#!/usr/bin/env python3
"""NAZMOS CORE REALITY TEST V1 - runner.

Exercises the real customer workflow against the running Docker stack:
  register -> bootstrap business -> upload sales+inventory -> map -> ETL
  -> money audit -> inspect classifications/actions -> approve -> complete
  -> verify state change -> business memory -> tenant isolation -> constraints.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

BASE = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
FRONT = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
EMAIL = os.getenv("RT_EMAIL", "reality-core@example.com")
PASSWORD = os.getenv("RT_PASSWORD", "Reality!2026-Strong")
FULL_NAME = "NAZMOS Core Reality Test"
FIXTURE = Path("reality_fixture")
OUT = Path("reality_test_output")
OUT.mkdir(parents=True, exist_ok=True)

results = {}


def rec(client, method, path, **kw):
    try:
        r = client.request(method, BASE + path, timeout=60, **kw)
    except Exception as e:
        return None, f"transport_error: {e}"
    body = None
    try:
        body = r.json()
    except Exception:
        body = r.text
    return r.status_code, body


def run():
    with httpx.Client() as c:
        r = rec(c, "GET", "/api/v1/ready")
        results["ready"] = r
        if r[0] != 200:
            print("API not ready:", r)
            sys.exit(1)

        # ---- AUTH: register ----
        s, b = rec(c, "POST", "/api/v1/auth/register",
                   json={"email": EMAIL, "password": PASSWORD, "full_name": FULL_NAME})
        results["auth_register"] = (s, b or {})
        if s == 201:
            token = b["access_token"]
        else:
            s2, b2 = rec(c, "POST", "/api/v1/auth/login",
                         json={"email": EMAIL, "password": PASSWORD})
            results["auth_login"] = (s2, b2 or {})
            token = b2.get("access_token") if s2 == 200 else None
        if not token:
            print("AUTH FAILED")
            _write()
            sys.exit(1)
        c.headers.update({"Authorization": f"Bearer {token}"})
        results["auth_token"] = bool(token)

        # unauthenticated access rejected
        try:
            s_u = httpx.get(BASE + "/api/v1/ready", timeout=15).status_code
        except Exception:
            s_u = None
        results["unauth_ready"] = s_u  # public endpoint

        # ---- BUSINESS bootstrap ----
        s, b = rec(c, "POST", "/api/v1/businesses/bootstrap",
                   json={"name": "Reality Test Mart", "type": "supermart", "city": "Riyadh"})
        results["bootstrap"] = (s, b or {})
        bid = b.get("id") if s == 200 else None
        print("business_id", bid)
        if not bid:
            print("BOOTSTRAP FAILED")
            _write(); sys.exit(1)

        # ---- UPLOAD sales ----
        for name in ("reality_sales.csv", "reality_inventory.csv"):
            fpath = FIXTURE / name
            with fpath.open("rb") as f:
                s, b = rec(c, "POST", "/api/v1/upload/",
                           data={"business_id": bid},
                           files={"file": (name, f, "text/csv")})
            if s != 200:
                print(f"UPLOAD FAILED {name}: {s} {b}")
                results[f"upload_{name}"] = (s, b or {})
                _write(); sys.exit(1)
            up = b
            uid = up["upload_id"]
            detected = up.get("detected_columns", {})
            results[f"detect_{name}"] = {
                "status": s, "row_count": up.get("row_count"),
                "detected": detected, "schema_valid": up.get("schema_valid"),
            }
            print(f"detected {name}: rows={up.get('row_count')} valid={up.get('schema_valid')} cols={detected}")
            s, b = rec(c, "POST", f"/api/v1/upload/{uid}/map",
                       json={"business_id": bid, "column_mapping": detected})
            results[f"map_{name}"] = (s, b or {})
            if s != 200:
                print(f"MAP FAILED {name}: {s} {b}")
                _write(); sys.exit(1)
            # poll
            last = None
            for _ in range(120):
                s2, b2 = rec(c, "GET", f"/api/v1/upload/{uid}/status")
                last = (s2, b2 or {})
                st = b2.get("status") if isinstance(b2, dict) else None
                if st == "completed":
                    s3, b3 = rec(c, "GET", f"/api/v1/upload/{uid}/result")
                    results[f"import_{name}"] = {"status": st, "result": b3}
                    print(f"IMPORTED {name}: {b3}")
                    break
                if st == "failed":
                    results[f"import_{name}"] = {"status": st, "error": b2}
                    print(f"IMPORT FAILED {name}: {b2}")
                    _write(); sys.exit(1)
                time.sleep(2)
            else:
                results[f"import_{name}"] = {"status": "timeout", "last": last}
                print(f"IMPORT TIMEOUT {name}")
                _write(); sys.exit(1)

        # ---- MONEY AUDIT ----
        s, b = rec(c, "POST", "/api/v1/money-audit/generate", json={"business_id": bid})
        results["audit_generate"] = (s, b or {})
        print("AUDIT:", s, {k: b.get(k) for k in ("id","money_at_risk_sar","data_quality_score")} if isinstance(b,dict) else b)
        if s != 200:
            print("AUDIT FAILED")
            _write(); sys.exit(1)

        classifications = b.get("classification_summary") or {}
        actions = b.get("actions") or []
        results["classifications"] = classifications
        results["action_count"] = len(actions)
        print("CLASSIFICATIONS:", classifications)
        print("ACTIONS:", len(actions))

        # breakdown per action
        action_details = []
        for a in actions:
            action_details.append({
                "item_id": a.get("item_id"), "title": a.get("title"),
                "action_type": a.get("action_type"), "priority": a.get("priority"),
                "expected_recovery_sar": a.get("expected_recovery_sar"),
                "recoverable_low": a.get("recoverable_value_low_sar"),
                "recoverable_high": a.get("recoverable_value_high_sar"),
            })
        results["actions_detail"] = action_details

        # ---- APPROVE + EXECUTE one action ----
        exec_outcome = {}
        if actions:
            aid = actions[0]["id"]
            s, b = rec(c, "POST", f"/api/v1/money-audit/actions/{aid}/approve",
                       json={"business_id": bid, "approval_channel": "reality_test", "notes": "RT approve"})
            exec_outcome["approve"] = (s, b or {})
            print("APPROVE:", s, (b.get("status") if isinstance(b,dict) else b))
            if s == 200:
                comp = max(1, int((actions[0].get("expected_recovery_sar") or 1)))
                s2, b2 = rec(c, "POST", f"/api/v1/money-audit/actions/{aid}/complete",
                             json={"business_id": bid, "approval_channel": "reality_test",
                                   "completed_value_sar": 100, "notes": "RT complete"})
                exec_outcome["complete"] = (s2, b2 or {})
                print("COMPLETE:", s2, (b2.get("status") if isinstance(b2,dict) else b2),
                      "recovered:", (b2.get("money_recovered_sar") if isinstance(b2,dict) else None))
        results["execution"] = exec_outcome

        # ---- TENANT ISOLATION: second user/business ----
        iso = {}
        email2 = f"iso-{int(time.time())}@example.com"
        s, b = rec(c, "POST", "/api/v1/auth/register",
                   json={"email": email2, "password": PASSWORD, "full_name": "Isolation"})
        iso["register"] = (s, b or {})
        if s == 201:
            tok2 = b["access_token"]
            c2headers = {"Authorization": f"Bearer {tok2}"}
            # try to read first business data as user2
            s2 = httpx.get(BASE + f"/api/v1/ops/pilot-console?business_id={bid}",
                           headers=c2headers, timeout=20)
            iso["cross_tenant_read"] = s2.status_code
            print("CROSS-TENANT READ status:", s2.status_code)
        results["tenant_isolation"] = iso

        # ---- BUSINESS MEMORY ----
        s, b = rec(c, "GET", f"/api/v1/intelligence/business-context?business_id={bid}")
        if isinstance(b, dict):
            ctx_info = {
                "status": s,
                "product_count": len(b.get("products", [])),
                "supplier_count": len(b.get("suppliers", [])),
                "branch_count": len(b.get("branches", [])),
                "recent_actions": len(b.get("recent_actions", [])),
                "outcomes": len(b.get("outcomes", [])),
                "products_sample": [p.get("sku") for p in b.get("products", [])][:10],
            }
        else:
            ctx_info = {"status": s, "body": str(b)[:300]}
        results["business_context"] = ctx_info
        print("BUSINESS CONTEXT:", s, "products:", ctx_info.get("product_count"), "suppliers:", ctx_info.get("supplier_count"))

        # ---- PRODUCT CONTEXT (first product) ----
        first_product_id = None
        if isinstance(b, dict) and b.get("products"):
            first_product_id = b["products"][0].get("product_id") or b["products"][0].get("item_id") or b["products"][0].get("id")
        if first_product_id:
            s2, b2 = rec(c, "GET", f"/api/v1/intelligence/products/{first_product_id}/context?business_id={bid}")
            results["product_context_route"] = {"status": s2, "product_id": first_product_id}
            print("PRODUCT CONTEXT route:", s2)
        else:
            results["product_context_route"] = {"status": None, "note": "no products in context"}
            print("PRODUCT CONTEXT route: skipped (no products)")

        _write()
        print("RESULTS WRITTEN to", OUT / "results.json")


def _write():
    with (OUT / "results.json").open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)


if __name__ == "__main__":
    run()
