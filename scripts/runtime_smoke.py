#!/usr/bin/env python3
"""Runtime smoke test for a running NazmOS deployment.

Requires API_BASE_URL. Optional ACCESS_TOKEN and BUSINESS_ID allow authenticated
checks. This does not mutate data except optional Money Audit generation when
RUN_MUTATION_CHECKS=true.
"""
from __future__ import annotations

import os
import sys
import requests

BASE = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
TOKEN = os.getenv("ACCESS_TOKEN", "")
BUSINESS_ID = os.getenv("BUSINESS_ID", "00000000-0000-0000-0000-000000000001")
RUN_MUTATION = os.getenv("RUN_MUTATION_CHECKS", "false").lower() == "true"
HEADERS = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}


def check(method: str, path: str, expected: set[int], **kwargs):
    url = BASE + path
    response = requests.request(method, url, headers=HEADERS, timeout=15, **kwargs)
    print(f"{method} {path} -> {response.status_code}")
    if response.status_code not in expected:
        print(response.text[:500])
        raise SystemExit(1)
    return response


def main():
    check("GET", "/health", {200})
    check("GET", "/api/v1/health", {200})
    ready = check("GET", "/api/v1/ready", {200}).json()
    print("readiness:", ready.get("status"), ready.get("checks"))

    # Unauthenticated/protected-route behavior if no token.
    if not TOKEN:
        check("GET", f"/api/v1/money-audit/current?business_id={BUSINESS_ID}", {401})
        print("No ACCESS_TOKEN supplied; authenticated smoke checks skipped.")
        return

    check("GET", f"/api/v1/money-audit/current?business_id={BUSINESS_ID}&auto_generate=false", {200, 404})
    check("GET", f"/api/v1/ops/pilot-console?business_id={BUSINESS_ID}", {200})
    check("GET", f"/api/v1/recovery-match/status?business_id={BUSINESS_ID}", {200, 402})

    if RUN_MUTATION:
        check("POST", "/api/v1/money-audit/generate", {200}, json={"business_id": BUSINESS_ID})

    print("Runtime smoke passed.")


if __name__ == "__main__":
    main()
