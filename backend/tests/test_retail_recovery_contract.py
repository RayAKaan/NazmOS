"""Production-pilot contract tests for NazmOS Retail Recovery.

These tests intentionally avoid a live database. They lock the bugs found during
workspace testing: route prefix issues, frontend/backend API drift, schema
detection errors, and legacy-term regressions.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
BANNED_TERMS = [
    "Attention" + "DB",
    "ATTENTION" + "_DB",
    "attention" + "_db",
    "attention" + "db",
    "ZA" + "TCA",
    "za" + "tca",
    "Mu" + "dad",
    "mu" + "dad",
    "Fa" + "toora",
    "fa" + "toora",
    "SA" + "MA",
    "lend" + "ing",
    "Lend" + "ing",
    "LEND" + "ING",
    "financ" + "ing",
    "Financ" + "ing",
    "FINANC" + "ING",
    "finance" + "_readiness",
    "finance" + "_partner",
    "charity" + "_ledger",
    "Charity" + "Ledger",
    "vat" + "_number",
]
BANNED_PATTERNS = re.compile("|".join(re.escape(term) for term in BANNED_TERMS))


def test_openapi_has_no_double_api_prefixes():
    from app.main import app

    paths = app.openapi()["paths"].keys()
    assert not [p for p in paths if "/api/v1/api/v1" in p]


def test_frontend_api_calls_exist_in_backend_openapi():
    from app.main import app

    schema = app.openapi()
    compiled = []
    for path in schema["paths"].keys():
        regex = "^" + re.sub(r"\\\{[^}]+\\\}", r"[^/]+", re.escape(path)) + "$"
        compiled.append((path, re.compile(regex)))

    frontend_root = ROOT / "frontend" / "src"
    calls = []
    for file_path in frontend_root.rglob("*"):
        if file_path.suffix not in {".ts", ".tsx"}:
            continue
        text = file_path.read_text(errors="ignore")
        for match in re.finditer(r"api\.(get|post|put|patch|delete)\(\s*([`\"])(.*?)(\2)", text, flags=re.S):
            method = match.group(1).upper()
            raw = match.group(3).replace("\n", "")
            if raw.startswith("http"):
                continue
            path = raw.split("?")[0]
            path = re.sub(r"\$\{[^}]+\}", "X", path)
            full_path = path if path.startswith("/api/v1") else "/api/v1" + path
            calls.append((str(file_path.relative_to(ROOT)), method, raw, full_path))

    missing = []
    for file_path, method, raw, full_path in calls:
        ok = any(regex.match(full_path) and method.lower() in schema["paths"][path] for path, regex in compiled)
        if not ok:
            missing.append((file_path, method, raw, full_path))

    assert calls, "No frontend API calls found; contract test is not exercising anything."
    assert missing == []


def test_sales_file_detection_is_not_misclassified_as_inventory_or_expiry():
    from app.services.schema_detector import SchemaDetector
    from app.services.data_normalizer import normalize_dataframe

    df = pd.DataFrame({
        "Date": ["2026-07-01"],
        "Product": ["Coffee Beans 250g"],
        "Qty": [2],
        "Total": ["SAR 50"],
        "Cost": ["15"],
    })

    detection = SchemaDetector().detect(df)
    assert detection["suggested_file_kind"] == "sales_history"
    assert detection["detected_columns"]["Date"] == "transaction_at"
    assert detection["detected_columns"]["Qty"] == "quantity"
    assert detection["detected_columns"]["Cost"] == "cost_price"

    normalized = normalize_dataframe(df, detection["detected_columns"])
    row = normalized.iloc[0].to_dict()
    assert row["item_name"] == "Coffee Beans 250g"
    assert row["quantity"] == 2
    assert row["unit_price"] == 25


def test_arabic_inventory_detection_maps_purchase_price_correctly():
    from app.services.schema_detector import SchemaDetector
    from app.services.data_normalizer import normalize_dataframe

    df = pd.DataFrame({
        "اسم المنتج": ["قهوة 250g"],
        "مخزون": [68],
        "سعر الشراء": ["15 ر.س"],
        "باركود": ["628000000001"],
        "تاريخ الصلاحية": ["2027-01-01"],
    })

    detection = SchemaDetector().detect(df)
    assert detection["suggested_file_kind"] == "inventory_snapshot"
    assert detection["detected_columns"]["اسم المنتج"] == "item_name"
    assert detection["detected_columns"]["مخزون"] == "current_stock"
    assert detection["detected_columns"]["سعر الشراء"] == "cost_price"
    assert detection["detected_columns"]["تاريخ الصلاحية"] == "expiry_date"

    normalized = normalize_dataframe(df, detection["detected_columns"])
    row = normalized.iloc[0].to_dict()
    assert row["item_name"] == "قهوة 250g"
    assert row["current_stock"] == 68
    assert row["cost_price"] == 15


def test_legacy_distraction_terms_are_not_reintroduced_in_source():
    ignored_dirs = {"node_modules", ".next", ".git", "__pycache__", ".pytest_cache", ".venv", "venv"}
    ignored_files = {"TESTING_REPORT.md"}  # the report may mention removed terms historically.
    matches = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.name in ignored_files:
            continue
        if any(part in ignored_dirs for part in path.parts):
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf", ".pyc", ".zip"}:
            continue
        try:
            text = path.read_text(errors="ignore")
        except Exception:
            continue
        if BANNED_PATTERNS.search(text):
            matches.append(str(path.relative_to(ROOT)))
    assert matches == []


def test_model_router_defaults_to_openrouter_not_vendor_url():
    from app.config import get_settings
    from app.services.llm_orchestrator import LLMOrchestrator

    settings = get_settings()
    assert settings.OPENROUTER_BASE_URL.rstrip("/") == "https://openrouter.ai/api/v1"
    assert settings.LLM_MODEL
    orchestrator = LLMOrchestrator()
    assert orchestrator._chat_url().startswith("https://openrouter.ai/api/v1/")
    assert "chat/completions" in orchestrator._chat_url()
