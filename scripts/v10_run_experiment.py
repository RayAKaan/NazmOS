#!/usr/bin/env python3
"""V10: Single-business longitudinal experiment runner.

Al Noor Supermarket & Convenience — 88 SKUs, 20 adversarial cases.
Triage-first AI: max 20 calls total across entire experiment.
Mode comparison: MODE_A baseline first, then MODE_A+B+C with AI.
6 checkpoints: d00, d07, d14, d30, d45, d60.
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from v10.evaluator import (
    GT, OM, classify_override, classify_decision, recovery_factor_for,
    score_mode_results, consumption_rate,
)

BASE = "http://localhost:8000"
DATA = ROOT / "sample_data" / "v10"
RESULTS = ROOT / "results" / "v10"
RESULTS.mkdir(parents=True, exist_ok=True)

RUN_TS = int(time.time())
PASSWORD = "AlNoorV10Test!"
OWNER_EMAIL = "alnoor@example.com"
BIZ_NAME = "Al Noor Supermarket & Convenience"
CHECKPOINTS = ["d00", "d07", "d14", "d30", "d45", "d60"]
CP_GAP_DAYS = {"d00": 0, "d07": 7, "d14": 14, "d30": 30, "d45": 45, "d60": 60}
AI_BUDGET = 10
EXECUTABLE = {"reorder", "restock", "reorder_critical", "price_change",
              "pricing_increase", "pricing_decrease", "discount", "transfer"}
BIZ_KEY = "al_noor_supermarket"
CONSTRAINTS = GT["constraint_expectations"].get(BIZ_KEY, {})

rng = random.Random("v10-outcome-noise")

_token: str | None = None
CURRENT_OWNER: str = ""


def psql(query: str) -> list[list[str]]:
    proc = subprocess.run(
        ["docker", "exec", "nazmos-postgres-1",
         "psql", "-U", "nazmos", "-d", "nazmos", "-A", "-F", "|", "-t", "-c", query],
        capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        print(f"  psql error: {proc.stderr[:200]}")
        return []
    return [line.split("|") for line in proc.stdout.strip().splitlines() if line]


def request(client: httpx.Client, method: str, path: str, **kw) -> httpx.Response:
    global _token, CURRENT_OWNER
    for _ in range(6):
        timeout = 600 if path.endswith(("ab-compare", "generate")) else 120
        r = client.request(method, BASE + path, timeout=timeout, **kw)
        if r.status_code == 401 and "/auth/" not in path:
            try:
                rl = client.post(BASE + "/api/v1/auth/login",
                                 json={"email": CURRENT_OWNER, "password": PASSWORD},
                                 timeout=60)
                if rl.status_code == 200:
                    _token = rl.json()["access_token"]
                    client.headers["Authorization"] = f"Bearer {_token}"
                    continue
            except Exception:
                pass
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", "20"))
            print(f"    429 {path}; waiting {wait}s")
            time.sleep(min(wait, 90) + 1)
            continue
        return r
    return r


def auth(client: httpx.Client, email: str | None = None, login_only: bool = False):
    global _token, CURRENT_OWNER
    email = email or OWNER_EMAIL
    CURRENT_OWNER = email
    if not login_only:
        r = request(client, "POST", "/api/v1/auth/register", json={
            "email": email, "password": PASSWORD, "full_name": "Al Noor"})
        if r.status_code == 201:
            _token = r.json()["access_token"]
            client.headers["Authorization"] = f"Bearer {_token}"
            return
    client.headers.pop("Authorization", None)
    r = request(client, "POST", "/api/v1/auth/login",
                json={"email": email, "password": PASSWORD})
    if r.status_code != 200 or "access_token" not in r.json():
        raise SystemExit(f"auth login failed for {email}: {r.status_code} {r.text[:200]}")
    _token = r.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {_token}"


def upload_and_ingest(client: httpx.Client, business_id: str, path: Path) -> bool:
    with path.open("rb") as f:
        up = request(client, "POST", "/api/v1/upload/",
                     data={"business_id": business_id},
                     files={"file": (path.name, f, "text/csv")})
    if up.status_code != 200:
        print(f"    UPLOAD FAIL {path.name}: {up.text[:150]}")
        return False
    j = up.json()
    upload_id, detected = j.get("upload_id"), j.get("detected_columns", {})
    request(client, "POST", f"/api/v1/upload/{upload_id}/map",
            json={"business_id": business_id, "column_mapping": detected})
    time.sleep(5)  # initial wait before polling
    deadline = time.time() + 300
    st = {}
    while time.time() < deadline:
        resp = request(client, "GET", f"/api/v1/upload/{upload_id}/status")
        if resp.status_code == 429:
            time.sleep(30)
            continue
        st = resp.json() if resp.status_code == 200 else {}
        if st.get("status") in ("completed", "failed"):
            break
        time.sleep(5)
    ok = st.get("status") == "completed"
    if not ok:
        print(f"    INGEST FAIL {path.name}: {st}")
    return ok


def seed_constraints(business_id: str) -> None:
    psql(f"""
        INSERT INTO subscriptions (id, business_id, plan, status,
            ai_queries_limit, locations_limit, team_members_limit, pos_integrations_limit)
        SELECT gen_random_uuid(), '{business_id}', 'enterprise', 'active', 9999, 99, 99, 99
        WHERE NOT EXISTS (SELECT 1 FROM subscriptions WHERE business_id='{business_id}');
    """)
    psql(f"UPDATE subscriptions SET plan='enterprise' WHERE business_id='{business_id}';")
    cj: dict = {}
    if CONSTRAINTS.get("cash_budget_sar") is not None:
        cj["cash_budget"] = CONSTRAINTS["cash_budget_sar"]
    if CONSTRAINTS.get("max_discount_pct") is not None:
        cj["max_discount_pct"] = CONSTRAINTS["max_discount_pct"]
    if CONSTRAINTS.get("blocked_discount_skus"):
        cj["blocked_discount_products"] = CONSTRAINTS["blocked_discount_skus"]
    if CONSTRAINTS.get("strategic_skus"):
        cj["strategic_products"] = CONSTRAINTS["strategic_skus"]
    if CONSTRAINTS.get("blocked_transfer_routes"):
        cj["blocked_transfer_routes"] = CONSTRAINTS["blocked_transfer_routes"]
    if CONSTRAINTS.get("maximum_purchase_amount_sar") is not None:
        cj["maximum_purchase_amount"] = CONSTRAINTS["maximum_purchase_amount_sar"]
    if cj:
        q = ("UPDATE businesses SET constraints_json="
             f"'{json.dumps(cj).replace(chr(39), chr(39)*2)}'::jsonb WHERE id='{business_id}';")
        psql(q)


def action_sku_map(audit_id: str) -> dict[str, str]:
    rows = psql(f"""
        SELECT a.id::text, i.sku FROM money_audit_actions a
        JOIN items i ON i.id = a.item_id
        WHERE a.audit_id='{audit_id}';
    """)
    return {r[0]: r[1] for r in rows}


def apply_consumption(business_id: str, prev_cp: str, cp: str) -> None:
    days = CP_GAP_DAYS[cp] - CP_GAP_DAYS[prev_cp]
    if days <= 0:
        return
    consumption = OM["daily_consumption_units_per_day"].get(BIZ_KEY, {})
    updates = []
    for sku, rate in consumption.items():
        c = rate
        if c <= 0:
            continue
        dec = round(c * days)
        if dec <= 0:
            continue
        updates.append(
            f"UPDATE inventory SET current_stock = GREATEST(0, current_stock - {dec}) "
            f"WHERE business_id='{business_id}' AND item_id IN "
            f"(SELECT id FROM items WHERE sku='{sku}');")
    if updates:
        psql("-- SIMULATED_CONSUMPTION\n" + "\n".join(updates))


def run_checkpoint(client: httpx.Client, business_id: str, cp: str) -> dict:
    rec: dict = {"checkpoint": cp, "business": BIZ_KEY}

    inv_path = DATA / f"{BIZ_KEY}_inventory_d0.csv"
    sales_path = DATA / f"{BIZ_KEY}_sales_{cp}.csv"
    files_ok = True
    if cp == "d00":
        files_ok &= upload_and_ingest(client, business_id, inv_path)
    files_ok &= upload_and_ingest(client, business_id, sales_path)
    rec["ingested"] = files_ok
    if not files_ok:
        return rec

    aud = request(client, "POST", "/api/v1/money-audit/generate",
                  json={"business_id": business_id})
    if aud.status_code != 200:
        print(f"    AUDIT FAIL: {aud.text[:150]}")
        rec["audit_error"] = aud.text[:200]
        return rec
    audit = aud.json()
    rec["audit_id"] = audit["id"]
    rec["money_at_risk_sar"] = audit.get("money_at_risk_sar")

    # A/B/C comparison (retry once if zero effective AI coverage)
    ab_body = {}
    attempts = []
    for attempt in range(2):
        t0 = time.time()
        ab = request(client, "POST", f"/api/v1/money-audit/{audit['id']}/ab-compare",
                     json={"max_ai_calls": AI_BUDGET})
        elapsed = round(time.time() - t0, 1)
        print(f"    ab-compare status={ab.status_code} elapsed={elapsed}s")
        if ab.status_code != 200:
            print(f"    ab-compare body: {ab.text[:300]}")
        ab_body = ab.json() if ab.status_code == 200 else {}
        cmp_ = ab_body.get("comparison") or {}
        eff = sum(cmp_.get(k, 0) or 0 for k in
                  ("ai_overrides", "ai_agreements", "ai_manual_reviews", "ai_low_confidence"))
        attempts.append({"attempt": attempt + 1, "elapsed_s": elapsed,
                         "effective_ai": eff, "error": ab_body.get("error"),
                         "ai_calls": cmp_.get("ai_total_calls") or ab_body.get("ai_total_calls")})
        if eff > 0:
            break
        time.sleep(35)
    rec["ab_attempts"] = attempts
    rec["ab_comparison"] = ab_body.get("comparison")
    rec["mode_a_raw"] = [{"sku": m.get("sku"), "final_decision": m.get("final_decision")}
                         for m in ab_body.get("mode_a", [])]
    rec["mode_b_raw"] = ab_body.get("mode_b", [])
    rec["mode_c_raw"] = [
        {"sku": m.get("sku"), "final_decision": m.get("final_decision"),
         "decision_source": m.get("decision_source")}
        for m in ab_body.get("mode_c", [])]

    a2s = action_sku_map(audit["id"])

    rec["eval_mode_a"] = score_mode_results(BIZ_KEY, rec["mode_a_raw"])
    rec["eval_mode_b"] = score_mode_results(
        BIZ_KEY, [{"sku": m.get("sku"), "final_decision": m.get("final_decision")}
                  for m in rec["mode_b_raw"]])
    rec["eval_mode_c"] = score_mode_results(BIZ_KEY, rec["mode_c_raw"])

    b_by_sku = {m.get("sku"): m for m in rec["mode_b_raw"]}
    overrides = []
    for m in rec["mode_a_raw"]:
        sku = m.get("sku")
        b = b_by_sku.get(sku) or {}
        det = m.get("final_decision")
        ai_final = b.get("final_decision")
        if ai_final is None:
            continue
        cls = classify_override(BIZ_KEY, sku, det, ai_final)
        overrides.append({
            "sku": sku, "deterministic": det, "mode_b_final": ai_final,
            "source": b.get("decision_source"), "classification": cls,
            "confidence": b.get("ai_confidence"),
            "reasoning_excerpt": (b.get("ai_reasoning") or "")[:240],
            "validation_reason": ((b.get("validation") or {}).get("reason") or "")[:200],
        })
    rec["overrides_b_vs_a"] = overrides

    c_by_sku = {m.get("sku"): m.get("final_decision") for m in rec["mode_c_raw"]}
    b_fin_by_sku = {m.get("sku"): m.get("final_decision") for m in rec["mode_b_raw"]}
    a_by_sku = {m.get("sku"): m.get("final_decision") for m in rec["mode_a_raw"]}
    adopted, adopted_source = {}, {}
    for sku in set(list(c_by_sku) + list(b_fin_by_sku) + list(a_by_sku)):
        pick = None
        src = ""
        for mode_name, table in (("C", c_by_sku), ("B", b_fin_by_sku), ("A", a_by_sku)):
            v = table.get(sku)
            if v:
                pick, src = v, mode_name
                break
        if pick:
            adopted[sku] = pick
            adopted_source[sku] = src
    rec["adopted_source_counts"] = {
        "C": sum(1 for v in adopted_source.values() if v == "C"),
        "B": sum(1 for v in adopted_source.values() if v == "B"),
        "A": sum(1 for v in adopted_source.values() if v == "A"),
    }

    chain = []
    actions = audit.get("actions", [])
    for act in actions:
        aid = act["id"]
        sku = a2s.get(aid, "")
        decision = adopted.get(sku)
        entry = {"action_id": aid, "sku": sku, "audit_action_type": act["action_type"],
                 "owner_decision": decision, "decided_by": adopted_source.get(sku)}
        if decision is None:
            chain.append(entry)
            continue
        norm = (decision or "").lower()
        if norm in EXECUTABLE and act["action_type"].lower() in EXECUTABLE:
            ap = request(client, "POST", f"/api/v1/money-audit/actions/{aid}/approve",
                         json={"business_id": business_id, "approval_channel": "v10_owner_adoption"})
            entry["approved"] = ap.status_code == 200
            ex = request(client, "POST", f"/api/v1/money-audit/actions/{aid}/execute",
                         json={"business_id": business_id})
            entry["executed"] = ex.status_code == 200
            expected = float(act.get("expected_recovery_sar") or 0) or \
                float(act.get("recoverable_value_high_sar") or 0)
            verdict = classify_decision(BIZ_KEY, sku, decision)
            factor = recovery_factor_for(verdict)
            reported = round(expected * factor * (1 + rng.uniform(-0.05, 0.05)), 2)
            cp_resp = request(client, "POST", f"/api/v1/money-audit/actions/{aid}/complete",
                              json={"business_id": business_id,
                                    "completed_value_sar": max(reported, 0),
                                    "approval_channel": "v10_SIMULATED_OUTCOME",
                                    "notes": f"[SIMULATED_OUTCOME verdict={verdict} decided_by={entry['decided_by']}]"})
            entry["completed"] = cp_resp.status_code == 200
            entry["simulated_actual_sar"] = max(reported, 0)
            entry["expected_sar"] = round(expected, 2)
            entry["verdict"] = verdict
        elif normalize_nothing(decision):
            rj = request(client, "POST", f"/api/v1/money-audit/actions/{aid}/reject",
                         json={"business_id": business_id,
                               "approval_channel": "v10_owner_do_nothing"})
            entry["rejected_as_do_nothing"] = rj.status_code == 200
        chain.append(entry)
    rec["chain"] = chain
    return rec


def normalize_nothing(d: str) -> bool:
    return (d or "").upper() in ("DO_NOTHING", "HOLD")


def main() -> None:
    master_path = RESULTS / "v10_experiment_master.json"
    master: dict = {"started": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "llm": "groq/openai-gpt-oss-120b via live stack",
                    "adoption": "C>B>A", "business": BIZ_KEY,
                    "checkpoints": CHECKPOINTS}
    if master_path.exists():
        try:
            existing = json.loads(master_path.read_text())
            merged = {**existing.get("checkpoints_data", {})}
            master["started"] = existing.get("started", master["started"])
            master["checkpoints_data"] = merged
            master["resumed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            pass

    resume_cp = os.getenv("RESUME_CP", "")

    with httpx.Client() as client:
        biz_id = None
        if resume_cp:
            rows = psql(f"SELECT id FROM businesses WHERE name='{BIZ_NAME}' ORDER BY created_at DESC LIMIT 1;")
            if rows:
                biz_id = rows[0][0]
            owner_rows = psql(f"SELECT u.email FROM businesses b JOIN users u ON u.id=b.owner_id "
                              f"WHERE b.name='{BIZ_NAME}' ORDER BY b.created_at DESC LIMIT 1;")
            if owner_rows:
                auth(client, owner_rows[0][0], login_only=True)
            print(f"RESUME from {resume_cp}")
            master["business_id"] = biz_id
        else:
            auth(client)
            r = request(client, "POST", "/api/v1/businesses/bootstrap", json={
                "name": BIZ_NAME, "type": "supermart", "city": "Riyadh"})
            biz_id = r.json().get("id")
            if not biz_id:
                raise SystemExit(f"bootstrap failed: {r.text[:200]}")
            seed_constraints(biz_id)
            master["business_id"] = biz_id
            master["owner"] = CURRENT_OWNER
            (RESULTS / "v10_experiment_master.json").write_text(
                json.dumps(master, indent=1, default=str))

        started = False
        for cp in CHECKPOINTS:
            if resume_cp and not started:
                started = (cp == resume_cp)
                if not started:
                    continue
            print(f"\n########## CHECKPOINT {cp} ##########")
            prev = CHECKPOINTS[max(0, CHECKPOINTS.index(cp) - 1)]
            if cp != "d00":
                apply_consumption(biz_id, prev, cp)
            rec = run_checkpoint(client, biz_id, cp)
            ev_a = rec.get("eval_mode_a", {})
            ev_b = rec.get("eval_mode_b", {})
            ev_c = rec.get("eval_mode_c", {})
            print(f"  A correct={ev_a.get('correct_decision_rate')} "
                  f"B correct={ev_b.get('correct_decision_rate')} "
                  f"C correct={ev_c.get('correct_decision_rate')}")
            ov = rec.get("overrides_b_vs_a", [])
            good = sum(1 for o in ov if o["classification"] == "GOOD_OVERRIDE")
            bad = sum(1 for o in ov if o["classification"] == "BAD_OVERRIDE")
            print(f"  overrides: {len(ov)} (good={good}, bad={bad})")
            (RESULTS / f"checkpoint_{cp}.json").write_text(
                json.dumps(rec, indent=1, default=str))
            master.setdefault("checkpoints_data", {})[cp] = {
                kk: vv for kk, vv in rec.items()
                if kk.startswith("eval_") or kk in ("ab_attempts", "adopted_source_counts")}
            (RESULTS / "v10_experiment_master.json").write_text(
                json.dumps(master, indent=1, default=str))
            if cp != CHECKPOINTS[-1]:
                print("  [WAIT] 10s cooldown between checkpoints...")
                time.sleep(10)

    print("\nV10 RUN COMPLETE. Results in results/v10/")


if __name__ == "__main__":
    main()
