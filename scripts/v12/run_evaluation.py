"""V12 AI-OFF Reality Test - Phase 9/10 evaluation runner.

Reads per-item DB metrics (results/v12/evidence/db_item_probe.tsv), computes
each GT SKU's classification with the ported oracle, and compares against:
  - ground_truth.json (authored intent)
  - master_expected.csv (realized expectation from generator)
  - actual money-audit actions (audit_current.json)
Then emits results/v12/evidence/evaluation.json and prints a table + assertions.
"""
import csv
import json
import os
from decimal import Decimal as D

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EVID = os.path.join(ROOT, "results", "v12", "evidence")
TSV = os.path.join(EVID, "db_item_probe.tsv")


# ported oracle (exact copy of classify_inventory)
def classify(*, stock, q30, prior, dsls, months):
    daily = q30 / D("30") if q30 > 0 else D("0")
    if q30 > 0 and months and len(months) >= 2:
        tot = sum(max(m, D("0")) for m in months)
        if tot > 0:
            peak = max(months)
            if (peak / tot) >= D("0.60"):
                return "SEASONAL"
    if q30 <= 0:
        is_dormant = (dsls is None) or (dsls is not None and dsls >= 60)
        if is_dormant and prior <= 0:
            return "DEAD"
        return "UNKNOWN"
    if stock <= 0 and daily > 0 and daily < D("3"):
        return "SLOW MOVING"
    if stock <= 0:
        return "HEALTHY"
    if daily >= D("1"):
        return "FAST"
    return "HEALTHY"


def load_db_metrics():
    m = {}
    with open(TSV, encoding="utf-16") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            if len(parts) < 6:
                continue
            sku, stock, q30, prior, dsls, monthly = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
            months = [D(x) for x in monthly.split(",") if x.strip() != ""] if monthly else []
            m[sku] = {
                "stock": D(stock or "0"),
                "qty30": D(q30 or "0"),
                "prior": D(prior or "0"),
                "dsls": (int(dsls) if dsls.strip() != "" else None),
                "months": months,
            }
    return m


def main():
    db = load_db_metrics()
    gt = json.load(open(os.path.join(ROOT, "results", "v12", "ground_truth.json"), encoding="utf-8"))
    gt_by = {c["sku"]: c for c in gt["cases"]}

    # master_expected (realized expectation)
    master = {}
    with open(os.path.join(ROOT, "sample_data", "v12", "master_expected.csv"), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            master[r["sku"]] = r

    # actual actions from audit_current.json
    audit = json.load(open(os.path.join(EVID, "audit_current.json"), encoding="utf-8"))
    audit = audit.get("audit", audit)
    actions = audit.get("actions") or []
    act_by = {}
    for a in actions:
        ev = a.get("evidence") or {}
        if isinstance(ev, str):
            try:
                ev = json.loads(ev)
            except Exception:
                ev = {}
        act_by[a.get("item_id")] = {
            "action_type": a.get("action_type"), "status": a.get("status"),
            "classification": ev.get("classification"),
            "recoverable_high": a.get("recoverable_value_high_sar"),
            "expected_recovery": a.get("expected_recovery_sar"),
        }

    summary = audit.get("summary")
    if isinstance(summary, str):
        summary = json.loads(summary)

    # map action item_id -> sku
    item_sku = {}
    # audit may include an items list; fall back to db metrics sku keys
    # We map actions to skus using evidence.sku when present
    for a in actions:
        ev = a.get("evidence") or {}
        if isinstance(ev, str):
            try:
                ev = json.loads(ev)
            except Exception:
                ev = {}
        sk = ev.get("sku") or ev.get("item_sku")
        if sk:
            item_sku[a.get("item_id")] = sk

    rows = []
    class_match = 0
    for sku in sorted(gt_by):
        c = gt_by[sku]
        dm = db.get(sku)
        cls = None
        if dm:
            cls = classify(stock=dm["stock"], q30=dm["qty30"], prior=dm["prior"],
                           dsls=dm["dsls"], months=dm["months"])
        exp_cls = c["expected_classification"]
        master_cls = master.get(sku, {}).get("expected_classification")
        exp_dec = c["expected_decision"]
        master_dec = master.get(sku, {}).get("expected_decision")
        expected_action = c["expected_primary_action"]
        actual_action = None
        actual_status = None
        # find actual action for this sku
        for aid, sk in item_sku.items():
            if sk == sku:
                actual_action = act_by[aid]["action_type"]
                actual_status = act_by[aid]["status"]
                break
        # classification match (GT intent vs DB-derived)
        cm = (cls == exp_cls) if cls else False
        if cm:
            class_match += 1
        rows.append({
            "sku": sku, "category": c["category"],
            "expected_classification": exp_cls, "db_classification": cls, "classification_match": cm,
            "master_classification": master_cls,
            "expected_decision": exp_dec, "master_decision": master_dec,
            "expected_primary_action": expected_action, "actual_primary_action": actual_action,
            "action_status": actual_status,
            "inputs": {"stock": dm["stock"] if dm else None, "qty30": dm["qty30"] if dm else None,
                       "prior": dm["prior"] if dm else None, "dsls": dm["dsls"] if dm else None,
                       "months": dm["months"] if dm else None},
        })

    # action coverage: which GT SKUs got an action, and did action_type match expected
    action_match = sum(1 for r in rows if r["actual_primary_action"] == r["expected_primary_action"])
    eval_data = {
        "summary": summary,
        "rows": rows,
        "class_match": class_match, "class_total": len(rows),
        "action_match": action_match, "gt_skus_with_action": sum(1 for r in rows if r["actual_primary_action"]),
        "financial": {
            "capital_at_risk_sar": summary.get("capital_at_risk_sar"),
            "revenue_at_risk_sar": summary.get("revenue_at_risk_sar"),
            "margin_leakage_sar": summary.get("margin_leakage_sar"),
            "recoverable_low_sar": summary.get("recoverable_value_low_sar"),
            "recoverable_high_sar": summary.get("recoverable_value_high_sar"),
            "expected_recovery_sar": summary.get("expected_recovery_sar"),
            "money_recovered_sar": summary.get("money_recovered_sar"),
            "headline_note": summary.get("headline_note"),
        },
    }
    out_path = os.path.join(EVID, "evaluation.json")
    json.dump(eval_data, open(out_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False, default=str)
    print("wrote", out_path)
    print(f"classification match (GT intent vs DB): {class_match}/{len(rows)}")
    print(f"action match (actual vs expected): {action_match}/{len(rows)}")
    print("\n--- per-GT-SKU table ---")
    print(f"{'SKU':<18}{'cat':<10}{'GT_cls':<10}{'DB_cls':<10}{'match':<6}{'expAct':<10}{'actAct':<9}{'status'}")
    for r in rows:
        print(f"{r['sku']:<18}{r['category']:<10}{r['expected_classification']:<10}"
              f"{str(r['db_classification']):<10}{str(r['classification_match']):<6}"
              f"{r['expected_primary_action']:<10}{str(r['actual_primary_action']):<9}{r['action_status']}")


if __name__ == "__main__":
    main()
