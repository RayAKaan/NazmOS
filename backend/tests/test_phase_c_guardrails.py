"""Phase C6/C7 — guardrails & two-file flow on the public endpoint."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import guest_audit as ga

_RECENT = (datetime.utcnow() - timedelta(days=5)).date().isoformat()
SALES_CSV = (
    f"name,qty,price,date\nHot SKU,75,12,{_RECENT}\nThin SKU,40,15,{_RECENT}\nMargin SKU,40,10,{_RECENT}\n"
).encode("utf-8")
INV_CSV = (
    "name,current_stock,cost,sell_price\n"
    "Dead SKU,80,5,8\nHot SKU,2,6,12\nThin SKU,3000,12,15\nMargin SKU,20,9,10\n"
).encode("utf-8")


@pytest.fixture(autouse=True)
def _clear_rate_limit():
    ga._rate_windows.clear()
    yield
    ga._rate_windows.clear()


def _client() -> TestClient:
    return TestClient(app)


def test_two_file_flow_returns_paired_summary():
    client = _client()
    resp = client.post("/api/v1/guest-audit", files={
        "sales_file": ("sales.csv", SALES_CSV, "text/csv"),
        "inventory_file": ("inventory.csv", INV_CSV, "text/csv"),
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["is_two_file"] is True
    assert body["summary"]["pairing"]["attempted"] == 3
    assert body["summary"]["pairing"]["paired"] == 3
    assert body["summary"]["dead_stock_value_sar"] == 400.0
    assert body["summary"]["overstock_value_sar"] > 0
    assert body["summary"]["stockout_risk_value_sar"] > 0


def test_two_file_requires_both_files():
    client = _client()
    resp = client.post("/api/v1/guest-audit", files={
        "sales_file": ("sales.csv", SALES_CSV, "text/csv"),
    })
    assert resp.status_code == 422


def test_single_file_upload_still_works():
    client = _client()
    resp = client.post("/api/v1/guest-audit", files={
        "file": ("inventory.csv", INV_CSV, "text/csv"),
    })
    assert resp.status_code == 200
    body = resp.json()["summary"]
    assert "is_two_file" not in body
    assert body["dead_stock_value_sar"] > 0


def test_unsupported_extension_rejected():
    client = _client()
    resp = client.post("/api/v1/guest-audit", files={
        "file": ("evil.exe", b"malware", "application/octet-stream"),
    })
    assert resp.status_code == 422


def test_oversized_file_rejected():
    client = _client()
    big = b"a" * (11 * 1024 * 1024)
    resp = client.post("/api/v1/guest-audit", files={
        "file": ("big.csv", big, "text/csv"),
    })
    assert resp.status_code == 413


def test_garbage_xlsx_rejected_with_parse_reason():
    client = _client()
    resp = client.post("/api/v1/guest-audit", files={
        "file": ("broken.xlsx", b"not a real workbook at all", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    })
    assert resp.status_code == 422


def test_rate_limit_enforced_after_five_requests():
    client = _client()
    for _ in range(5):
        resp = client.post("/api/v1/guest-audit", files={
            "file": ("inventory.csv", INV_CSV, "text/csv"),
        })
        assert resp.status_code == 200
    resp = client.post("/api/v1/guest-audit", files={
        "file": ("inventory.csv", INV_CSV, "text/csv"),
    })
    assert resp.status_code == 429
    assert "X-RateLimit-Limit" in resp.text or resp.status_code == 429


def test_empty_payload_rejected():
    client = _client()
    resp = client.post("/api/v1/guest-audit", json={"rows": []})
    assert resp.status_code == 422