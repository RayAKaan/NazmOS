import requests, json
import sys
sys.path.insert(0, r"H:\NAZMOS\nazmos\scripts\v12")
from run_pipeline import BASE, AUTH, login

tok = login().get("access_token")
h = {"Authorization": "Bearer " + tok}
bid = "6d5312ba-c4c3-4e15-bacc-ab29a85adfa7"
MA = "/api/v1/money-audit"

discount_action = "8826fc06-52e2-4787-8996-1ef2a8c05dfd"   # V12-OVERSTOCK-003
reorder_action = "5fb877e5-c090-47dd-821d-ee918b0b275f"    # V12-PO-001

def post(path, body=None):
    r = requests.post(BASE + path, headers=h, json=body or {}, timeout=120)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text

print("=== 1) EXECUTE unapproved (should be blocked 400) ===")
sc, b = post(f"{MA}/actions/{discount_action}/execute", {"business_id": bid})
print("status", sc, str(b)[:200])

print("\n=== 2) SIMULATE discount action (should be estimate_only) ===")
sc, b = post(f"{MA}/actions/{discount_action}/simulate", {"business_id": bid})
print("status", sc, "estimate_only=", b.get("estimate_only") if isinstance(b, dict) else b)
if isinstance(b, dict) and b.get("options"):
    for o in b["options"][:3]:
        print("   option:", json.dumps(o, default=str)[:220])

print("\n=== 3) APPROVE + EXECUTE DISCOUNT (V12-OVERSTOCK-003) ===")
sc, b = post(f"{MA}/actions/{discount_action}/approve", {"business_id": bid})
print("approve", sc, str(b)[:160])
sc, b = post(f"{MA}/actions/{discount_action}/execute", {"business_id": bid})
print("execute", sc)
# pull action row post-execution
import subprocess
q = f"SELECT status, completed_value_sar, notes FROM money_audit_actions WHERE id='{discount_action}'"
out = subprocess.run(["docker","exec","nazmos-postgres-1","psql","-U","nazmos","-d","nazmos","-t","-A","-c",q],
                     capture_output=True, text=True).stdout.strip()
print("action row:", out)

print("\n=== 4) APPROVE + EXECUTE RESTOCK (V12-PO-001, stock was 0, 200 inbound) ===")
sc, b = post(f"{MA}/actions/{reorder_action}/approve", {"business_id": bid})
print("approve", sc, str(b)[:160])
sc, b = post(f"{MA}/actions/{reorder_action}/execute", {"business_id": bid})
print("execute", sc, str(b)[:120])
q2 = "SELECT i.sku, inv.current_stock FROM items i JOIN inventory inv ON inv.item_id=i.id AND inv.business_id=i.business_id WHERE i.sku='V12-PO-001'"
out2 = subprocess.run(["docker","exec","nazmos-postgres-1","psql","-U","nazmos","-d","nazmos","-t","-A","-c",q2],
                     capture_output=True, text=True).stdout.strip()
print("V12-PO-001 current_stock after RESTOCK:", out2)
q3 = f"SELECT status, completed_value_sar, notes FROM money_audit_actions WHERE id='{reorder_action}'"
print("reorder action row:", subprocess.run(["docker","exec","nazmos-postgres-1","psql","-U","nazmos","-d","nazmos","-t","-A","-c",q3],
                     capture_output=True, text=True).stdout.strip())
