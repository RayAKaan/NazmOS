#!/usr/bin/env python3
"""V2 Reality Test — Steps 4+5: 5-Business Run + MODE_A vs MODE_B experiment.

For each of 5 businesses (real PostgreSQL, Redis, Celery, real Gemini):
  upload -> Celery ingest -> money audit -> /ab-compare (MODE_A vs MODE_B vs
  MODE_C on the SAME evidence, real LLM) -> approve -> execute -> verify
  business-state change in PostgreSQL -> complete with reported outcome ->
  record prediction error.

Produces v2_reality_test_results.json with:
  - per-business per-action chain records
  - MODE_A/B/C comparison metrics
  - AI value-add analysis (deterministic scoring of overridden decisions,
    explicitly labelled ESTIMATE)

Usage:
  python scripts/v2_step4_reality_run.py
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
PASSWORD = "SecureV2Run123!"
SAMPLES = [
    ROOT / "sample_data" / "demo_ksa_retail_sales_q3_2026.csv",
    ROOT / "sample_data" / "demo_ksa_retail_inventory_aug_2026.csv",
]
BUSINESSES = [
    {"type": "baqala", "name": "V2 Al-Olaya Baqala", "city": "Riyadh"},
    {"type": "supermart", "name": "V2 Corniche Supermarket", "city": "Jeddah"},
    {"type": "cafe", "name": "V2 Dhahran Cafe", "city": "Dhahran"},
    {"type": "restaurant", "name": "V2 Taif Restaurant", "city": "Taif"},
    {"type": "retail", "name": "V2 Khobar General Retail", "city": "Khobar"},
]
EXECUTABLE_TYPES = {"reorder", "restock", "reorder_critical", "price_change",
                    "pricing_increase", "pricing_decrease", "discount"}


def psql(query: str) -> list[list[str]]:
    proc = subprocess.run(
        ["docker", "exec", "nazmos-postgres-1",
         "psql", "-U", "nazmos", "-d", "nazmos", "-A", "-F", "|", "-t", "-c", query],
        capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        return []
    return [line.split("|") for line in proc.stdout.strip().splitlines() if line]


def request(client: httpx.Client, method: str, path: str, **kw) -> httpx.Response:
    for attempt in range(6):
        timeout = 400 if path.endswith("ab-compare") else 120
        r = client.request(method, BASE + path, timeout=timeout, **kw)
        if r.status_code == 429:
            retry_after = int(r.headers.get("Retry-After", "15"))
            print(f"    429 on {path}; waiting {retry_after}s...")
            time.sleep(min(retry_after, 90) + 1)
            continue
        if r.status_code >= 400:
            print(f"    {method} {path} -> {r.status_code}: {r.text[:200]}")
        return r
    return r


def score_decision(item: dict, decision: str) -> float:
    """Deterministic ESTIMATE scoring of a candidate decision (SAR).

    Explicitly an estimate layer used ONLY to compare two candidate decisions
    on the same evidence. Formulas:
      REORDER        : protects stockout revenue = stockout_days*velocity*sell
                       capped at revenue_at_risk
      DISCOUNT       : liquidates dead value = inventory_value * margin_pct
      TRANSFER       : recovers low-bound recoverable
      PRICE_CHANGE   : margin leakage share = inventory_value * margin_pct * 0.5
      RECOVERY_MATCH : mid recoverable
      DO_NOTHING / MANUAL_REVIEW / INSUFFICIENT_EVIDENCE : 0
    """
    inv_val = float(item.get("inventory_value_sar") or 0)
    sell = float(item.get("sell_price_sar") or 0)
    vel = float(item.get("daily_velocity") or 0)
    so_days = float(item.get("stockout_days") or 0)
    margin = float(item.get("margin_pct") or 0)
    rec_low = float(item.get("recoverable_low_sar") or 0)
    rec_high = float(item.get("recoverable_high_sar") or 0)

    if decision == "REORDER":
        return min(so_days * vel * sell, float(item.get("revenue_at_risk_sar") or 0))
    if decision == "DISCOUNT":
        return inv_val * max(margin * 0.5, 0.05)
    if decision == "TRANSFER":
        return rec_low if rec_low > 0 else inv_val * 0.25
    if decision == "PRICE_CHANGE":
        return inv_val * max(margin, 0) * 0.5
    if decision == "RECOVERY_MATCH":
        return (rec_low + rec_high) / 2 if rec_high > 0 else inv_val * 0.2
    return 0.0


def run_business(biz_def: dict, idx: int, owner_email: str) -> dict:
    print(f"\n=== [{idx+1}/5] {biz_def['name']} ({biz_def['type']}) ===")
    email = owner_email
    rec: dict = {"business": biz_def, "email": email}

    with httpx.Client() as client:
        login = request(client, "POST", "/api/v1/auth/login", json={
            "email": email, "password": PASSWORD})
        token = login.json()["access_token"]
        client.headers.update({"Authorization": f"Bearer {token}"})

        biz = request(client, "POST", "/api/v1/businesses/bootstrap", json=biz_def)
        business_id = biz.json()["id"]
        rec["business_id"] = business_id

        # Upload + Celery ingest
        ingest_ok = True
        for sample in SAMPLES:
            with sample.open("rb") as f:
                up = request(client, "POST", "/api/v1/upload/",
                             data={"business_id": business_id},
                             files={"file": (sample.name, f, "text/csv")})
            upload_id = up.json().get("upload_id")
            detected = up.json().get("detected_columns", {})
            request(client, "POST", f"/api/v1/upload/{upload_id}/map",
                    json={"business_id": business_id, "column_mapping": detected})
            deadline = time.time() + 180
            status = {}
            while time.time() < deadline:
                status = request(client, "GET",
                                 f"/api/v1/upload/{upload_id}/status").json()
                if status.get("status") in ("completed", "failed"):
                    break
                time.sleep(2)
            if status.get("status") != "completed":
                ingest_ok = False
        rec["ingest_completed"] = ingest_ok

        audit_resp = request(client, "POST", "/api/v1/money-audit/generate",
                             json={"business_id": business_id})
        audit = audit_resp.json()
        audit_id = audit["id"]
        actions = audit.get("actions", [])
        rec["audit_id"] = audit_id
        rec["action_count"] = len(actions)
        rec["money_at_risk_sar"] = audit.get("money_at_risk_sar")
        print(f"  audit={audit_id} actions={len(actions)} "
              f"at_risk={rec['money_at_risk_sar']}")

        # ---- Step 5: MODE_A vs MODE_B vs MODE_C (REAL Gemini) --------------
        # Gemini free tier enforces requests-per-minute; the backend circuit
        # breaker opens if calls fail repeatedly. Pace each attempt and retry
        # once after the breaker recovery window when coverage was lost.
        def _effective_ai_coverage(body: dict) -> int:
            c = body.get("comparison") or {}
            return sum([
                c.get("ai_overrides", 0) or 0,
                c.get("ai_agreements", 0) or 0,
                c.get("ai_manual_reviews", 0) or 0,
            ])

        ab_attempts = []
        for attempt in range(2):
            time.sleep(20 if attempt == 0 else 40)
            t0 = time.time()
            ab = request(client, "POST", f"/api/v1/money-audit/{audit_id}/ab-compare")
            ab_elapsed = time.time() - t0
            ab_body = ab.json() if ab.status_code == 200 else {}
            ab_attempts.append({
                "attempt": attempt + 1,
                "elapsed_s": round(ab_elapsed, 1),
                "effective_ai": _effective_ai_coverage(ab_body),
                "error": ab_body.get("error"),
            })
            if ab_body and _effective_ai_coverage(ab_body) > 0:
                break
        rec["ab_compare_attempts"] = ab_attempts
        cmp_data = ab_body.get("comparison", {})
        rec["ab_compare"] = {
            "http_ok": ab.status_code == 200,
            "error": ab_body.get("error"),
            "elapsed_s": round(ab_elapsed, 1),
            "comparison": cmp_data,
            "ai_total_calls": ab_body.get("ai_total_calls")
                              or cmp_data.get("ai_total_calls"),
            "items_evaluated": cmp_data.get("items_evaluated"),
        }
        print(f"  A/B done in {ab_elapsed:.0f}s | overrides={cmp_data.get('ai_overrides')} "
              f"agreements={cmp_data.get('ai_agreements')} "
              f"constraint_rejections={cmp_data.get('constraint_rejections')}")

        # AI value-add estimate on overrides
        mode_a_by_sku = {m["sku"]: m for m in ab_body.get("mode_a", [])}
        mode_b = ab_body.get("mode_b", [])
        items_pkg = {}
        ev = request(client, "GET", f"/api/v1/money-audit/{audit_id}/evidence")
        if ev.status_code == 200:
            items_pkg = {i.get("sku"): i for i in ev.json().get("items", [])}
        overrides = []
        ai_value_add = 0.0
        ai_harm = 0.0
        for m in mode_b:
            src = m.get("decision_source", "")
            if not src.startswith("AI_"):
                continue
            item = items_pkg.get(m["sku"], {})
            det_dec = m.get("deterministic_decision")
            final_dec = m.get("final_decision")
            s_det = score_decision(item, det_dec)
            s_ai = score_decision(item, final_dec)
            delta = round(s_ai - s_det, 2)
            if delta >= 0:
                ai_value_add += delta
            else:
                ai_harm += abs(delta)
            overrides.append({
                "sku": m["sku"], "deterministic": det_dec, "ai_final": final_dec,
                "source": src, "confidence": m.get("ai_confidence"),
                "score_deterministic_sar": round(s_det, 2),
                "score_ai_sar": round(s_ai, 2),
                "delta_sar_ESTIMATE": delta,
                "reasoning_excerpt": (m.get("ai_reasoning") or "")[:220],
            })
        rec["ai_overrides_detail"] = overrides
        rec["ai_value_add_sar_ESTIMATE"] = round(ai_value_add, 2)
        rec["ai_harm_sar_ESTIMATE"] = round(ai_harm, 2)

        # ---- Step 4 chain: approve -> execute -> verify state -> complete --
        chain = []
        executed = 0
        candidates = [a for a in actions
                      if a.get("item_id") and a.get("action_type") in EXECUTABLE_TYPES]
        fallbacks = [a for a in actions if a.get("item_id")]
        chosen = (candidates + fallbacks)[:2]  # up to 2 per business
        for a in chosen:
            step_rec = {
                "action_id": a["id"], "type": a["action_type"],
                "predicted_expected_sar": a.get("expected_recovery_sar"),
                "recoverable_high_sar": a.get("recoverable_value_high_sar"),
                "item_id": a["item_id"],
            }
            ap = request(client, "POST",
                         f"/api/v1/money-audit/actions/{a['id']}/approve",
                         json={"business_id": business_id,
                               "approval_channel": "v2_reality_run"})
            step_rec["approved"] = ap.status_code == 200

            pre = psql(f"SELECT current_stock FROM inventory WHERE "
                       f"item_id='{a['item_id']}' AND business_id='{business_id}';")
            pre_stock = float(pre[0][0]) if pre and pre[0][0] else None
            ex = request(client, "POST",
                         f"/api/v1/money-audit/actions/{a['id']}/execute",
                         json={"business_id": business_id})
            post = psql(f"SELECT current_stock FROM inventory WHERE "
                        f"item_id='{a['item_id']}' AND business_id='{business_id}';")
            post_stock = float(post[0][0]) if post and post[0][0] else None
            step_rec["executed_http_ok"] = ex.status_code == 200
            step_rec["state_change"] = {
                "pre_stock": pre_stock, "post_stock": post_stock,
                "mutated": (pre_stock is not None and post_stock is not None
                            and abs((post_stock or 0) - pre_stock) > 1e-9),
            }

            expected = float(a.get("expected_recovery_sar") or 0)
            basis = expected or float(a.get("recoverable_value_high_sar") or 0)
            reported = round(basis * 0.85, 2) if basis > 0 else 50.0
            cp = request(client, "POST",
                         f"/api/v1/money-audit/actions/{a['id']}/complete",
                         json={"business_id": business_id,
                               "completed_value_sar": reported,
                               "approval_channel": "v2_reality_run"})
            step_rec["completed"] = cp.status_code == 200
            step_rec["reported_actual_sar"] = reported

            ofr = psql(f"SELECT delta::text FROM outcome_feedback WHERE "
                       f"business_id='{business_id}' ORDER BY created_at DESC LIMIT 1;")
            if ofr:
                try:
                    d = json.loads(ofr[0][0])
                    step_rec["prediction_error"] = d.get("prediction_error")
                    step_rec["prediction_error_pct"] = d.get("prediction_error_pct")
                except Exception:
                    pass
            if step_rec["executed_http_ok"]:
                executed += 1
            chain.append(step_rec)
            print(f"  action {a['action_type']}: approved={step_rec['approved']} "
                  f"mutated={step_rec['state_change']['mutated']} "
                  f"err%={step_rec.get('prediction_error_pct')}")
        rec["chain"] = chain
        rec["executed_count"] = executed

    return rec


def main() -> None:
    all_results = []
    # One shared owner account: auth_register is IP-limited to 3/5min, so a
    # fresh user per business trips the limiter. One user may own many
    # businesses via /bootstrap.
    owner_email = f"v2-owner-{int(time.time())}@example.com"
    with httpx.Client() as boot:
        reg = request(boot, "POST", "/api/v1/auth/register", json={
            "email": owner_email, "password": PASSWORD, "full_name": "V2 Reality Owner"})
        assert reg.status_code == 201, f"owner registration failed: {reg.text[:200]}"
    print(f"owner={owner_email}")

    for i, b in enumerate(BUSINESSES):
        try:
            all_results.append(run_business(b, i, owner_email))
        except SystemExit:
            raise
        except Exception as exc:
            print(f"BUSINESS FAILED: {exc}")
            all_results.append({"business": b, "fatal_error": str(exc)})
        time.sleep(3)

    total_executed = sum(r.get("executed_count", 0) for r in all_results)
    total_overrides = sum(len(r.get("ai_overrides_detail", [])) for r in all_results)
    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "llm_provider": "google/gemini-2.5-flash-lite (USE_MOCK_LLM=false)",
        "businesses": len(all_results),
        "total_actions_executed": total_executed,
        "total_ai_overrides": total_overrides,
        "ai_value_add_sar_ESTIMATE_total": sum(
            r.get("ai_value_add_sar_ESTIMATE", 0) for r in all_results),
        "ai_harm_sar_ESTIMATE_total": sum(
            r.get("ai_harm_sar_ESTIMATE", 0) for r in all_results),
        "note": "All recovery figures are SIMULATION/ESTIMATE until measured "
                "against a live retailer. Value-add scoring formulas are "
                "deterministic estimates defined in score_decision().",
    }
    out = {"summary": summary, "businesses": all_results}
    out_path = ROOT / "v2_reality_test_results.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSTEP4/5 RESULT: businesses={len(all_results)} "
          f"executed={total_executed} overrides={total_overrides}")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
