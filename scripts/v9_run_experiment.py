#!/usr/bin/env python3
"""V9 Longitudinal Experiment Runner (P3).

Runs MODE_A / MODE_B / MODE_C against identical states at 6 virtual checkpoints
for 5 adversarial businesses, using REAL Groq (gpt-oss-120b) via the live stack.

Per checkpoint per business:
  upload sales window (+inventory at d00) -> Celery ingest -> audit ->
  /ab-compare {max_ai_calls} (real AI) -> evaluate vs ground truth ->
  owner adoption C>B>A -> approve/execute/reject accordingly ->
  complete with SIMULATED outcome -> persist everything.

Between checkpoints, baseline consumption from scripts/v9/outcome_model.json is
applied to inventory via psql (labeled SIMULATED_CONSUMPTION).

Outputs: results/v9/checkpoint_<cp>.json + v9_experiment_master.json
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from v9.evaluator import (  # noqa: E402
    GT, classify_override, classify_decision, recovery_factor_for,
    score_mode_results, consumption_rate,
)

BASE = "http://localhost:8000"
DATA = ROOT / "sample_data" / "v9"
RESULTS = ROOT / "results" / "v9"
RESULTS.mkdir(parents=True, exist_ok=True)

RUN_TS = int(time.time())
PASSWORD = "SecureV9Run123!"
def owner_email(biz_key: str) -> str:
    return f"v9-{biz_key}-{RUN_TS}@example.com"
CHECKPOINTS = ["d00", "d07", "d14", "d30", "d45", "d60"]
CP_GAP_DAYS = {"d00": 0, "d07": 7, "d14": 14, "d30": 30, "d45": 45, "d60": 60}
AI_BUDGET = 6          # triaged AI calls per mode per audit
EXECUTABLE = {"reorder", "restock", "reorder_critical", "price_change",
              "pricing_increase", "pricing_decrease", "discount"}
BUSINESSES = list(GT["businesses"].keys())
CONSTRAINTS = GT["constraint_expectations"]

rng = random.Random("v9-outcome-noise")

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
            # JWT expired mid-run: re-login and retry once with a fresh token
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
    """Register-or-login. One owner PER BUSINESS (bootstrap is first-store-only).
    login_only=True skips register (for resume where users already exist)."""
    global _token, CURRENT_OWNER
    email = email or owner_email("main")
    CURRENT_OWNER = email
    if not login_only:
        r = request(client, "POST", "/api/v1/auth/register", json={
            "email": email, "password": PASSWORD, "full_name": "V9 Experimenter"})
        if r.status_code == 201:
            _token = r.json()["access_token"]
            client.headers["Authorization"] = f"Bearer {_token}"
            return
    # Clear stale token before login to avoid header interference
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
    deadline = time.time() + 240
    st = {}
    while time.time() < deadline:
        st = request(client, "GET", f"/api/v1/upload/{upload_id}/status").json()
        if st.get("status") in ("completed", "failed"):
            break
        time.sleep(2)
    ok = st.get("status") == "completed"
    if not ok:
        print(f"    INGEST FAIL {path.name}: {st}")
    return ok


def seed_constraints(business_id: str, biz_key: str) -> None:
    """Seed owner constraints AND simulate a paid plan (uploads needed for a
    6-checkpoint longitudinal run exceed the free tier by design)."""
    # Ensure the subscription row exists (get_or_create makes it lazily on
    # first upload — an UPDATE alone would race and silently no-op).
    psql(f"""
        INSERT INTO subscriptions (id, business_id, plan, status,
            ai_queries_limit, locations_limit, team_members_limit, pos_integrations_limit)
        SELECT gen_random_uuid(), '{business_id}', 'enterprise', 'active', 9999, 99, 99, 99
        WHERE NOT EXISTS (SELECT 1 FROM subscriptions WHERE business_id='{business_id}');
    """)
    psql(f"UPDATE subscriptions SET plan='enterprise' WHERE business_id='{business_id}';")
    spec = CONSTRAINTS.get(biz_key, {})
    cj: dict = {}
    if spec.get("cash_budget_sar") is not None:
        cj["cash_budget"] = spec["cash_budget_sar"]
    if spec.get("max_discount_pct") is not None:
        cj["max_discount_pct"] = spec["max_discount_pct"]
    if spec.get("blocked_discount_skus"):
        # map SKUs to item ids after items exist; store SKUs now and again later
        cj["blocked_discount_products"] = spec["blocked_discount_skus"]
    if spec.get("strategic_skus"):
        cj["strategic_products"] = spec["strategic_skus"]
    if spec.get("blocked_transfer_routes"):
        cj["blocked_transfer_routes"] = spec["blocked_transfer_routes"]
    if spec.get("max_purchase_amount_sar") is not None:
        cj["maximum_purchase_amount"] = spec["max_purchase_amount_sar"]
    if not cj:
        return
    import json as _j
    q = ("UPDATE businesses SET constraints_json="
         f"'{_j.dumps(cj).replace(chr(39), chr(39)*2)}'::jsonb WHERE id='{business_id}';")
    psql(q)


def seed_inbound_po(business_id: str, sku: str, qty: int) -> None:
    rows = psql(f"""
        INSERT INTO purchase_orders (id, business_id, supplier_id, po_number,
            status, total_sar, items_json, expected_delivery, created_at, updated_at)
        SELECT gen_random_uuid(), '{business_id}', inv.supplier_id,
               'PO-V9-{sku}', 'confirmed', 0,
               '[{{\"sku\": \"{sku}\", \"quantity\": {qty}}}]'::jsonb,
               NOW() + INTERVAL '1 day', NOW(), NOW()
        FROM inventory inv JOIN items i ON i.id = inv.item_id
        WHERE inv.business_id='{business_id}' AND i.sku='{sku}'
        LIMIT 1 RETURNING id;
    """)
    print(f"    inbound PO for {sku}: {'seeded' if rows else 'NOT seeded'}")


def action_sku_map(audit_id: str) -> dict[str, str]:
    rows = psql(f"""
        SELECT a.id::text, i.sku FROM money_audit_actions a
        JOIN items i ON i.id = a.item_id
        WHERE a.audit_id='{audit_id}';
    """)
    return {r[0]: r[1] for r in rows}


def apply_consumption(biz_key: str, business_id: str, prev_cp: str, cp: str) -> None:
    days = CP_GAP_DAYS[cp] - CP_GAP_DAYS[prev_cp]
    if days <= 0:
        return
    updates = []
    for sku, rate in GT["businesses"][biz_key]["skus"].items():
        c = consumption_rate(biz_key, sku)
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


def run_checkpoint_business(client: httpx.Client, biz_key: str, business_id: str,
                            cp: str) -> dict:
    rec: dict = {"checkpoint": cp, "business": biz_key}

    inv_path = DATA / f"{biz_key}_inventory_d0.csv"
    sales_path = DATA / f"{biz_key}_sales_{cp}.csv"
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

    # Real-AI A/B/C comparison (retry once if zero effective AI coverage)
    ab_body = {}
    attempts = []
    for attempt in range(2):
        t0 = time.time()
        ab = request(client, "POST", f"/api/v1/money-audit/{audit['id']}/ab-compare",
                     json={"max_ai_calls": AI_BUDGET})
        elapsed = round(time.time() - t0, 1)
        ab_body = ab.json() if ab.status_code == 200 else {}
        cmp_ = ab_body.get("comparison") or {}
        eff = sum(cmp_.get(k, 0) or 0 for k in
                  ("ai_overrides", "ai_agreements", "ai_manual_reviews", "ai_low_confidence"))
        attempts.append({"attempt": attempt + 1, "elapsed_s": elapsed,
                         "effective_ai": eff, "error": ab_body.get("error"),
                         "ai_calls": cmp_.get("ai_total_calls") or ab_body.get("ai_total_calls")})
        if eff > 0:
            break
        time.sleep(35)  # circuit-breaker recovery window
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

    # Evaluate all three modes against ground truth
    rec["eval_mode_a"] = score_mode_results(biz_key, rec["mode_a_raw"])
    rec["eval_mode_b"] = score_mode_results(
        biz_key, [{"sku": m.get("sku"), "final_decision": m.get("final_decision")}
                  for m in rec["mode_b_raw"]])
    rec["eval_mode_c"] = score_mode_results(biz_key, rec["mode_c_raw"])

    # Override analysis B vs A on every triaged SKU
    b_by_sku = {m.get("sku"): m for m in rec["mode_b_raw"]}
    overrides = []
    for m in rec["mode_a_raw"]:
        sku = m.get("sku")
        b = b_by_sku.get(sku) or {}
        det = m.get("final_decision")
        ai_final = b.get("final_decision")
        if ai_final is None:
            continue
        cls = classify_override(biz_key, sku, det, ai_final)
        overrides.append({
            "sku": sku, "deterministic": det, "mode_b_final": ai_final,
            "source": b.get("decision_source"), "classification": cls,
            "confidence": b.get("ai_confidence"),
            "reasoning_excerpt": (b.get("ai_reasoning") or "")[:240],
            "validation_reason": ((b.get("validation") or {}).get("reason") or "")[:200],
        })
    rec["overrides_b_vs_a"] = overrides

    # Owner adoption C>B>A per sku
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

    # Execute according to adoption
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
                         json={"business_id": business_id, "approval_channel": "v9_owner_adoption"})
            entry["approved"] = ap.status_code == 200
            ex = request(client, "POST", f"/api/v1/money-audit/actions/{aid}/execute",
                         json={"business_id": business_id})
            entry["executed"] = ex.status_code == 200
            expected = float(act.get("expected_recovery_sar") or 0) or \
                float(act.get("recoverable_value_high_sar") or 0)
            verdict = classify_decision(biz_key, sku, decision)
            factor = recovery_factor_for(verdict)
            reported = round(expected * factor * (1 + rng.uniform(-0.05, 0.05)), 2)
            cp_resp = request(client, "POST", f"/api/v1/money-audit/actions/{aid}/complete",
                              json={"business_id": business_id,
                                    "completed_value_sar": max(reported, 0),
                                    "approval_channel": "v9_SIMULATED_OUTCOME",
                                    "notes": f"[SIMULATED_OUTCOME verdict={verdict} decided_by={entry['decided_by']}]"})
            entry["completed"] = cp_resp.status_code == 200
            entry["simulated_actual_sar"] = max(reported, 0)
            entry["expected_sar"] = round(expected, 2)
            entry["verdict"] = verdict
        elif normalize_nothing(decision):
            rj = request(client, "POST", f"/api/v1/money-audit/actions/{aid}/reject",
                         json={"business_id": business_id,
                               "approval_channel": "v9_owner_do_nothing"})
            entry["rejected_as_do_nothing"] = rj.status_code == 200
        chain.append(entry)
    rec["chain"] = chain
    return rec


def normalize_nothing(d: str) -> bool:
    return (d or "").upper() in ("DO_NOTHING", "HOLD")


def resolve_business_ids(client: httpx.Client) -> dict[str, str]:
    """Find existing V9 businesses by name (resume mode)."""
    ids = {}
    TYPE_MAP_NICE = {
        "B1_healthy_supermarket": "V9 Healthy Supermarket",
        "B2_poor_baqala": "V9 Poor Baqala",
        "B3_growing_supermarket": "V9 Growing Supermarket",
        "B4_seasonal_retailer": "V9 Seasonal Retailer",
        "B5_cash_constrained_restaurant": "V9 Cash Constrained Restaurant",
    }
    for biz_key, nice in TYPE_MAP_NICE.items():
        rows = psql(f"SELECT id FROM businesses WHERE name='{nice}' ORDER BY created_at DESC LIMIT 1;")
        if rows:
            ids[biz_key] = rows[0][0]
    return ids


def main() -> None:
    import os
    master_path = RESULTS / "v9_experiment_master.json"
    master: dict = {"started": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "llm": "groq/openai-gpt-oss-120b via live stack",
                    "adoption": "C>B>A",
                    "checkpoints": CHECKPOINTS, "businesses": {}}
    if master_path.exists():
        try:
            existing = json.loads(master_path.read_text())
            # preserve earlier checkpoint summaries; new ones overwrite by key
            merged = {**existing.get("checkpoints_data", {})}
            master["started"] = existing.get("started", master["started"])
            master["checkpoints_data"] = merged
            master["resumed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            pass

    resume_cp = os.getenv("RESUME_CP", "")
    resume_biz = os.getenv("RESUME_BIZ", "")

    with httpx.Client() as client:
        biz_ids: dict[str, str] = {}
        TYPE_MAP = {
            "B1_healthy_supermarket": "supermart",
            "B2_poor_baqala": "baqala",
            "B3_growing_supermarket": "grocery",
            "B4_seasonal_retailer": "retail",
            "B5_cash_constrained_restaurant": "restaurant",
        }
        if resume_cp:
            biz_ids = resolve_business_ids(client)
            missing = [k for k in BUSINESSES if k not in biz_ids]
            if missing:
                raise SystemExit(f"resume could not find businesses: {missing}")
            # Load owner emails directly from DB (master may be stale)
            resume_owners: dict[str, str] = {}
            TYPE_MAP_NICE2 = {
                "B1_healthy_supermarket": "V9 Healthy Supermarket",
                "B2_poor_baqala": "V9 Poor Baqala",
                "B3_growing_supermarket": "V9 Growing Supermarket",
                "B4_seasonal_retailer": "V9 Seasonal Retailer",
                "B5_cash_constrained_restaurant": "V9 Cash Constrained Restaurant",
            }
            for bk, nice in TYPE_MAP_NICE2.items():
                rows = psql(
                    f"SELECT u.email FROM businesses b JOIN users u ON u.id=b.owner_id "
                    f"WHERE b.name='{nice}' ORDER BY b.created_at DESC LIMIT 1;")
                if rows:
                    resume_owners[bk] = rows[0][0]
            print(f"RESUME from {resume_cp} (skip biz <= {resume_biz or '-'})")
            master["businesses"] = {bk: {"business_id": biz_ids[bk], "owner": resume_owners.get(bk, "")}
                                    for bk in BUSINESSES}
        else:
            # ONE OWNER PER BUSINESS: /bootstrap returns the owner's first
            # store, so five businesses require five owners.
            for biz_key in BUSINESSES:
                nice = biz_key.split("_", 1)[1].replace("_", " ").title()
                auth(client, owner_email(biz_key))
                r = request(client, "POST", "/api/v1/businesses/bootstrap", json={
                    "name": f"V9 {nice}", "type": TYPE_MAP[biz_key],
                    "city": "Riyadh"})
                bid = r.json().get("id")
                if not bid:
                    raise SystemExit(f"bootstrap failed for {biz_key}: {r.text[:200]}")
                biz_ids[biz_key] = bid
                seed_constraints(bid, biz_key)
                master["businesses"][biz_key] = {"business_id": bid, "owner": CURRENT_OWNER}
                time.sleep(2)
            # B3 inbound PO fixture (case B)
            seed_inbound_po(biz_ids["B3_growing_supermarket"], "GRW-OIL-03", 60)
            # Save master immediately so resume can find owner emails
            (RESULTS / "v9_experiment_master.json").write_text(
                json.dumps(master, indent=1, default=str))

        started = False
        for cp in CHECKPOINTS:
            if resume_cp and not started:
                started = (cp == resume_cp)
                if not started:
                    continue
            print(f"\n########## CHECKPOINT {cp} ##########")
            cp_rec = {}
            prev = CHECKPOINTS[max(0, CHECKPOINTS.index(cp) - 1)]
            for biz_key in BUSINESSES:
                if resume_cp and cp == resume_cp and resume_biz:
                    if BUSINESSES.index(biz_key) <= BUSINESSES.index(resume_biz):
                        continue
                bid = biz_ids[biz_key]
                print(f"\n=== {biz_key} @ {cp} ===")
                auth_email = resume_owners.get(biz_key) if resume_cp else owner_email(biz_key)
                auth(client, auth_email, login_only=bool(resume_cp))  # this business's owner session
                if cp != "d00":
                    apply_consumption(biz_key, bid, prev, cp)
                rec = run_checkpoint_business(client, biz_key, bid, cp)
                cp_rec[biz_key] = rec
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
                (RESULTS / f"checkpoint_{cp}_{biz_key}.json").write_text(
                    json.dumps(rec, indent=1, default=str))
            master.setdefault("checkpoints_data", {})[cp] = {
                k: {kk: vv for kk, vv in v.items()
                    if kk.startswith("eval_") or kk in ("ab_attempts", "adopted_source_counts")}
                for k, v in cp_rec.items()}
            (RESULTS / "v9_experiment_master.json").write_text(
                json.dumps(master, indent=1, default=str))

    print("\nV9 RUN COMPLETE. Results in results/v9/")


if __name__ == "__main__":
    main()
