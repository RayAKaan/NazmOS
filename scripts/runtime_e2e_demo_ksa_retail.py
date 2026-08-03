#!/usr/bin/env python3
"""End-to-end NazmOS runtime test using realistic KSA retail demo data.

This script uploads synthetic but realistic Saudi supermarket data and runs
the full Money Audit workflow. It is designed to surface real recovery signals
(stockouts, expiry risk, margin issues) without touching real merchant files.

Requires a running backend + Postgres. Zero-cost mode is fine
(USE_CELERY=false, USE_REDIS=false).

Example:
  cd backend && alembic upgrade head && cd ..
  python scripts/runtime_e2e_demo_ksa_retail.py

Environment:
  API_BASE_URL=http://localhost:8000
  E2E_EMAIL=demo-retail@example.com
  E2E_PASSWORD=SecureDemo123!
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
EMAIL = os.getenv("E2E_EMAIL", "demo-retail@example.com")
PASSWORD = os.getenv("E2E_PASSWORD", "SecureDemo123!")
FULL_NAME = os.getenv("E2E_FULL_NAME", "NazmOS KSA Retail Demo")
SAMPLES = [
    ROOT / "sample_data" / "demo_ksa_retail_sales_q3_2026.csv",
    ROOT / "sample_data" / "demo_ksa_retail_inventory_aug_2026.csv",
]


def fail(message: str) -> None:
    print(f"ERROR: {message}")
    raise SystemExit(1)


def request(client: httpx.Client, method: str, path: str, **kwargs) -> httpx.Response:
    response = client.request(method, BASE + path, timeout=60, **kwargs)
    print(f"{method} {path} -> {response.status_code}")
    if response.status_code >= 400:
        print(response.text[:1500])
    return response


def register_or_login(client: httpx.Client) -> str:
    payload = {"email": EMAIL, "password": PASSWORD, "full_name": FULL_NAME}
    response = request(client, "POST", "/api/v1/auth/register", json=payload)
    if response.status_code == 201:
        return response.json()["access_token"]
    response = request(client, "POST", "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if response.status_code != 200:
        fail("Could not register or login demo user")
    return response.json()["access_token"]


def bootstrap_business(client: httpx.Client) -> str:
    response = request(client, "POST", "/api/v1/businesses/bootstrap", json={
        "name": "Nazmak Mart - KSA Demo",
        "type": "supermart",
        "city": "Riyadh",
    })
    if response.status_code != 200:
        fail("Could not bootstrap business")
    business_id = response.json()["id"]
    print("business_id", business_id)
    return business_id


def upload_and_import(client: httpx.Client, business_id: str, file_path: Path) -> dict:
    if not file_path.exists():
        fail(f"Demo file missing: {file_path}")
    with file_path.open("rb") as f:
        response = request(
            client,
            "POST",
            "/api/v1/upload/",
            data={"business_id": business_id},
            files={"file": (file_path.name, f, "text/csv")},
        )
    if response.status_code != 200:
        fail(f"Upload failed: {file_path.name}")
    upload = response.json()
    upload_id = upload["upload_id"]
    detected = upload.get("detected_columns", {})
    print(file_path.name, "rows", upload.get("row_count"), "detected", detected)
    if not detected:
        fail(f"No columns detected for {file_path.name}")

    response = request(
        client,
        "POST",
        f"/api/v1/upload/{upload_id}/map",
        json={"business_id": business_id, "column_mapping": detected},
    )
    if response.status_code != 200:
        fail(f"Mapping failed for {file_path.name}")

    deadline = time.time() + 180
    last_status = None
    while time.time() < deadline:
        status_response = request(client, "GET", f"/api/v1/upload/{upload_id}/status")
        if status_response.status_code != 200:
            fail(f"Could not poll upload status for {file_path.name}")
        status = status_response.json()
        last_status = status
        print("upload status", file_path.name, status.get("status"), status.get("progress"), status.get("row_count_imported"))
        if status.get("status") == "completed":
            result = request(client, "GET", f"/api/v1/upload/{upload_id}/result")
            if result.status_code != 200:
                fail(f"Could not fetch upload result for {file_path.name}")
            print("upload result", result.json())
            return result.json()
        if status.get("status") == "failed":
            fail(f"Upload processing failed for {file_path.name}: {status}")
        time.sleep(2)
    fail(f"Upload did not complete within 180s. Last status: {last_status}")


def generate_money_audit(client: httpx.Client, business_id: str) -> dict:
    response = request(client, "POST", "/api/v1/money-audit/generate", json={"business_id": business_id})
    if response.status_code != 200:
        fail("Money Audit generation failed")
    audit = response.json()
    print("audit", {
        "id": audit.get("id"),
        "money_at_risk_sar": audit.get("money_at_risk_sar"),
        "actions": len(audit.get("actions", [])),
        "data_quality_score": audit.get("data_quality_score"),
        "summary": audit.get("summary"),
    })
    return audit


def approve_and_complete_first_action(client: httpx.Client, business_id: str, audit: dict) -> None:
    actions = audit.get("actions", [])
    if not actions:
        print("No audit actions generated; review whether the demo data triggers recovery signals.")
        return
    action_id = actions[0]["id"]
    response = request(client, "POST", f"/api/v1/money-audit/actions/{action_id}/approve", json={
        "business_id": business_id,
        "approval_channel": "demo_ksa_retail",
        "notes": "Approved via KSA retail demo run",
    })
    if response.status_code != 200:
        fail("Could not approve first action")
    response = request(client, "POST", f"/api/v1/money-audit/actions/{action_id}/complete", json={
        "business_id": business_id,
        "approval_channel": "demo_ksa_retail",
        "completed_value_sar": max(1, int(actions[0].get("expected_recovery_sar") or 1)),
        "notes": "Completed via KSA retail demo run",
    })
    if response.status_code != 200:
        fail("Could not complete first action")
    updated = response.json()
    print("money_approved_sar", updated.get("money_approved_sar"), "money_recovered_sar", updated.get("money_recovered_sar"))


def main() -> None:
    print("=" * 60)
    print("NazmOS KSA Retail Demo Run")
    print("=" * 60)
    with httpx.Client() as client:
        health = request(client, "GET", "/health")
        if health.status_code != 200:
            fail("Backend health check failed")
        token = register_or_login(client)
        client.headers.update({"Authorization": f"Bearer {token}"})
        business_id = bootstrap_business(client)
        results = []
        for sample in SAMPLES:
            results.append(upload_and_import(client, business_id, sample))
        audit = generate_money_audit(client, business_id)
        approve_and_complete_first_action(client, business_id, audit)
        ops = request(client, "GET", f"/api/v1/ops/pilot-console?business_id={business_id}")
        if ops.status_code != 200:
            fail("Pilot Ops console failed")
    print("=" * 60)
    print("NazmOS KSA retail demo E2E passed.")
    print("=" * 60)


if __name__ == "__main__":
    main()
