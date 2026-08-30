#!/usr/bin/env python3
"""V2 Reality Test — Step 3: Persistence Proof.

Proves at runtime:
  P1. Celery async ingestion completes against real PostgreSQL.
  P2. Approval -> Execution mutates real business state (inventory.current_stock).
  P3. Completion persists a predicted-vs-actual outcome row to outcome_feedback.
  P4. Outcome survives a backend container restart (restart-survival).
  P5. Evidence endpoint reads persisted outcomes back from PostgreSQL.

Ground truth is read from PostgreSQL via psql INSIDE the container,
never from API responses alone.

Usage:
  python scripts/v2_step3_persistence_proof.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
EMAIL = os.getenv("V2_EMAIL", "v2-persistence@example.com")
PASSWORD = os.getenv("V2_PASSWORD", "SecureV2Proof123!")
SAMPLES = [
    ROOT / "sample_data" / "demo_ksa_retail_sales_q3_2026.csv",
    ROOT / "sample_data" / "demo_ksa_retail_inventory_aug_2026.csv",
]

results: list[tuple[str, bool, str]] = []


def record(step: str, ok: bool, detail: str = "") -> None:
    results.append((step, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'} | {step}" + (f" | {detail}" if detail else ""))


def fail(msg: str) -> None:
    print(f"FATAL: {msg}")
    raise SystemExit(1)


def request(client: httpx.Client, method: str, path: str, **kwargs) -> httpx.Response:
    r = client.request(method, BASE + path, timeout=60, **kwargs)
    if r.status_code >= 400:
        print(f"  {method} {path} -> {r.status_code}: {r.text[:300]}")
    return r


def psql(query: str) -> list[dict]:
    """Run SQL inside the postgres container, return rows as dicts."""
    proc = subprocess.run(
        ["docker", "exec", "nazmos-postgres-1",
         "psql", "-U", "nazmos", "-d", "nazmos", "-A", "-F", "|", "-t", "-c", query],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        fail(f"psql failed: {proc.stderr[:300]}")
    rows = []
    for line in proc.stdout.strip().splitlines():
        parts = line.split("|")
        rows.append({f"c{i}": p for i, p in enumerate(parts)})
    return rows


def main() -> None:
    # --- Setup: auth + business + upload ---------------------------------
    with httpx.Client() as client:
        health = request(client, "GET", "/health")
        if health.status_code != 200:
            fail("backend not healthy")
        reg = request(client, "POST", "/api/v1/auth/register", json={
            "email": EMAIL, "password": PASSWORD, "full_name": "V2 Persistence Proof"})
        if reg.status_code == 201:
            token = reg.json()["access_token"]
        else:
            login = request(client, "POST", "/api/v1/auth/login", json={
                "email": EMAIL, "password": PASSWORD})
            token = login.json()["access_token"]
        client.headers.update({"Authorization": f"Bearer {token}"})

        biz = request(client, "POST", "/api/v1/businesses/bootstrap", json={
            "name": f"V2 Persistence Proof {int(time.time())}",
            "type": "grocery", "city": "Riyadh"})
        if biz.status_code != 200:
            fail("bootstrap failed")
        business_id = biz.json()["id"]
        print(f"business_id={business_id}")

        # --- P1: Celery ingestion on real stack --------------------------
        for sample in SAMPLES:
            with sample.open("rb") as f:
                up = request(client, "POST", "/api/v1/upload/",
                             data={"business_id": business_id},
                             files={"file": (sample.name, f, "text/csv")})
            if up.status_code != 200:
                fail(f"upload failed: {sample.name}")
            upload_id = up.json()["upload_id"]
            detected = up.json().get("detected_columns", {})
            mp = request(client, "POST", f"/api/v1/upload/{upload_id}/map",
                         json={"business_id": business_id, "column_mapping": detected})
            if mp.status_code != 200:
                fail(f"mapping failed: {sample.name}")
            deadline = time.time() + 180
            status = {}
            while time.time() < deadline:
                st = request(client, "GET", f"/api/v1/upload/{upload_id}/status")
                status = st.json()
                if status.get("status") in ("completed", "failed"):
                    break
                time.sleep(2)
            record(
                f"P1 celery ingest {sample.name}",
                status.get("status") == "completed",
                f"rows={status.get('row_count_imported')}",
            )

        audit_resp = request(client, "POST", "/api/v1/money-audit/generate",
                             json={"business_id": business_id})
        if audit_resp.status_code != 200:
            fail("audit generation failed")
        audit = audit_resp.json()
        audit_id = audit["id"]
        actions = audit.get("actions", [])
        print(f"audit={audit_id} actions={len(actions)}")

        # Prefer an executable action linked to an item (reorder/restock)
        target = None
        for a in actions:
            if a.get("item_id") and a.get("action_type") in ("reorder", "restock", "reorder_critical"):
                target = a
                break
        if not target:
            target = next((a for a in actions if a.get("item_id")), None)
        if not target:
            fail("no actionable item-linked action found")
        action_id = target["id"]
        item_id = target["item_id"]
        print(f"target action={action_id} type={target['action_type']} item={item_id}")

        # Ground truth: pre-execution stock from PostgreSQL
        pre_rows = psql(
            f"SELECT current_stock FROM inventory WHERE item_id='{item_id}' AND business_id='{business_id}';")
        pre_stock = float(pre_rows[0]["c0"]) if pre_rows and pre_rows[0]["c0"] not in ("", None) else None
        print(f"pre_exec current_stock={pre_stock}")

        # --- P2a: approve --------------------------------------------------
        ap = request(client, "POST", f"/api/v1/money-audit/actions/{action_id}/approve",
                     json={"business_id": business_id, "approval_channel": "v2_reality_test"})
        record("P2a approve", ap.status_code == 200)

        # --- P2b: execute -> business-state mutation ------------------------
        ex = request(client, "POST", f"/api/v1/money-audit/actions/{action_id}/execute",
                     json={"business_id": business_id})
        post_rows = psql(
            f"SELECT current_stock FROM inventory WHERE item_id='{item_id}' AND business_id='{business_id}';")
        post_stock = float(post_rows[0]["c0"]) if post_rows and post_rows[0]["c0"] not in ("", None) else None
        state_mutated = (
            ex.status_code == 200
            and pre_stock is not None and post_stock is not None
            and abs(post_stock - pre_stock) > 1e-9
        )
        record("P2b execute mutated business state", state_mutated,
               f"{pre_stock} -> {post_stock}")

        exec_rows = psql(
            "SELECT count(*) FROM executed_actions WHERE entity_id='" + item_id + "';")
        has_audit_trail = exec_rows and int(exec_rows[0]["c0"]) > 0
        record("P2c executed_actions audit trail exists", bool(has_audit_trail),
               f"count={exec_rows[0]['c0'] if exec_rows else '?'}")

        # --- P3: complete -> outcome_feedback persistence -------------------
        expected_val = float(target.get("expected_recovery_sar") or 0)
        reported_actual = round(expected_val * 0.8, 2) if expected_val > 0 else 42.5
        cp = request(client, "POST", f"/api/v1/money-audit/actions/{action_id}/complete",
                     json={"business_id": business_id,
                           "completed_value_sar": reported_actual,
                           "approval_channel": "v2_reality_test",
                           "notes": "V2 persistence proof completion"})
        record("P3a complete accepted", cp.status_code == 200)

        of_rows = psql(
            f"SELECT decision_type, predicted_outcome::text, actual_outcome::text, delta::text "
            f"FROM outcome_feedback WHERE business_id='{business_id}' "
            f"ORDER BY created_at DESC;")
        record("P3b outcome_feedback row persisted", len(of_rows) > 0,
               f"rows={len(of_rows)}")
        if of_rows:
            delta = json.loads(of_rows[0].get("c3") or "{}")
            err = delta.get("prediction_error_pct")
            expected_stored = json.loads(of_rows[0].get("c1") or "{}").get("expected_recovery_sar")
            print(f"  stored prediction_error_pct={err} expected_basis={expected_stored}")
            record("P3c prediction error computed & stored", err is not None,
                   f"error_pct={err}")

        # --- P4: restart-survival -------------------------------------------
        print("restarting backend container...")
        rc = subprocess.run(["docker", "restart", "nazmos-backend-1"],
                            capture_output=True, text=True, timeout=120)
        if rc.returncode != 0:
            fail("backend restart failed")
        deadline = time.time() + 180
        ready = False
        while time.time() < deadline:
            try:
                r = httpx.get(BASE + "/api/v1/ready", timeout=10)
                if r.status_code == 200 and r.json().get("status") == "ready":
                    ready = True
                    break
            except Exception:
                pass
            time.sleep(3)
        record("P4a backend restarted & ready", ready)

        of_after = psql(
            f"SELECT count(*) FROM outcome_feedback WHERE business_id='{business_id}';")
        survived = of_after and int(of_after[0]["c0"]) == len(of_rows)
        record("P4b outcome survived restart", bool(survived),
               f"count={of_after[0]['c0'] if of_after else '?'}")

        # --- P5: evidence endpoint reads persisted outcomes ------------------
        ev = request(client, "GET", f"/api/v1/money-audit/{audit_id}/evidence")
        ev_ok = ev.status_code == 200
        hist_count = 0
        if ev_ok:
            body = ev.json()
            hist = body.get("historical_outcomes") or body.get("previous_outcomes") or []
            hist_count = len(hist)
        record("P5 evidence endpoint reads outcomes from PG", ev_ok and hist_count > 0,
               f"historical_outcomes={hist_count}")

    # --- Summary ------------------------------------------------------------
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\nSTEP3 RESULT: {passed}/{total} passed")
    for step, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'} {step} {detail}")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
