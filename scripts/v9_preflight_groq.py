#!/usr/bin/env python3
"""V9 P0 preflight: validate Groq structured-JSON output + latency."""
from __future__ import annotations

import json
import os
import sys
import time

import httpx

KEY = os.getenv("GROQ_API_KEY", "")
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM = (
    "You are a retail inventory analyst. Respond with ONLY valid JSON, no markdown fences."
)
USER = (
    'Item: SKU-9 "Yogurt 500g". Classification: FAST. stockout_days: 5. current_stock: 6. '
    "daily_velocity: 20/day. supplier_lead_time_days: 2. "
    'Decide one action from ["REORDER","DISCOUNT","TRANSFER","DO_NOTHING","PRICE_CHANGE",'
    '"RECOVERY_MATCH","MANUAL_REVIEW"]. '
    'Return JSON: {"decision": "...", "confidence": 0.0-1.0, "reasoning": "one sentence", '
    '"evidence_ids": [], "risk_flags": [], "recommended_action": null}'
)


def main() -> int:
    if not KEY:
        print("PREFLIGHT_FAIL: GROQ_API_KEY not set")
        return 2
    print(f"PREFLIGHT: model={MODEL} key_prefix={KEY[:8]}...")
    start = time.time()
    r = httpx.post(
        URL,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        json={
            "model": MODEL,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": USER}],
            "temperature": 0.1,
            "max_tokens": 300,
        },
        timeout=45,
    )
    elapsed = (time.time() - start) * 1000
    print(f"HTTP {r.status_code} in {elapsed:.0f}ms")
    if r.status_code != 200:
        print("PREFLIGHT_FAIL:", r.text[:400])
        return 2
    d = r.json()
    text = d["choices"][0]["message"]["content"]
    usage = d.get("usage", {})
    cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        print("RAW:", text[:300])
        print("PREFLIGHT_FAIL: unparseable JSON")
        return 1
    decision = parsed.get("decision", "").upper()
    ok = decision == "REORDER" and isinstance(parsed.get("confidence"), (int, float))
    print(f"PARSED: decision={decision} confidence={parsed.get('confidence')}")
    print(f"USAGE: {json.dumps(usage)}")
    if ok:
        print(f"PREFLIGHT_PASS: Groq structured JSON valid ({elapsed:.0f}ms)")
        return 0
    print(f"PREFLIGHT_PARTIAL: parsed but unexpected decision (got {decision})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
