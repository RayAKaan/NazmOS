#!/usr/bin/env python3
"""V2 Reality Test pre-flight: validate real Gemini API key before burning quota."""
from __future__ import annotations

import json
import os
import sys
import time

import httpx

KEY = os.getenv("GOOGLE_AI_API_KEY", "")
MODEL = os.getenv("GOOGLE_AI_MODEL", "gemini-2.5-flash-lite")
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

PROMPT = (
    'You are a retail inventory analyst. Respond with ONLY valid JSON, no markdown fences.\n'
    'Item: SKU-123 "Almarai UHT Milk 1L". Classification: FAST. Stockout days last month: 6. '
    "Current stock: 4 units. Daily velocity: 12/day. Supplier lead time: 2 days.\n"
    'Decide one action from ["REORDER","DISCOUNT","TRANSFER","DO_NOTHING","MANUAL_REVIEW"]. '
    'Return JSON: {"decision": "...", "confidence": 0.0-1.0, "reasoning": "one sentence"}'
)


def main() -> int:
    if not KEY:
        print("PREFLIGHT_FAIL: GOOGLE_AI_API_KEY not set")
        return 2
    print(f"PREFLIGHT: testing model={MODEL} key_prefix={KEY[:6]}... key_len={len(KEY)}")
    payload = {
        "contents": [{"parts": [{"text": PROMPT}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 200},
    }
    start = time.time()
    try:
        resp = httpx.post(URL, params={"key": KEY}, json=payload, timeout=30)
    except Exception as exc:
        print(f"PREFLIGHT_FAIL: request error: {exc}")
        return 2
    elapsed = (time.time() - start) * 1000
    print(f"HTTP {resp.status_code} in {elapsed:.0f}ms")
    if resp.status_code != 200:
        body = resp.text[:500]
        print(f"PREFLIGHT_FAIL: non-200 response: {body}")
        return 2
    data = resp.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        usage = data.get("usageMetadata", {})
        cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(cleaned)
        decision = parsed.get("decision", "").upper()
        valid_decisions = {"REORDER", "DISCOUNT", "TRANSFER", "DO_NOTHING", "MANUAL_REVIEW"}
        ok = decision in valid_decisions and isinstance(parsed.get("confidence"), (int, float))
        print(f"RAW_RESPONSE: {text[:300]}")
        print(f"PARSED: decision={decision} confidence={parsed.get('confidence')}")
        print(f"USAGE: {json.dumps(usage)}")
        if ok:
            print(f"PREFLIGHT_PASS: real Gemini responded with valid structured JSON ({elapsed:.0f}ms)")
            return 0
        print("PREFLIGHT_FAIL: response JSON invalid or decision not allowed")
        return 1
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        print(f"PREFLIGHT_FAIL: unexpected response shape: {exc}")
        print(json.dumps(data)[:500])
        return 1


if __name__ == "__main__":
    sys.exit(main())
