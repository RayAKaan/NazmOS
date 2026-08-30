"""Evaluate a pilot summary JSON without inventing financial value."""
from __future__ import annotations
import json, sys

def main(path: str):
    data=json.load(open(path, encoding="utf-8"))
    baseline=data.get("baseline") or {}
    current=data.get("current") or {}
    result={"business_id":data.get("business_id"),"financial_value_claimed_sar":0.0,
            "outcomes_recorded":data.get("outcomes_recorded",0),
            "approved_or_completed_actions":data.get("approved_or_completed_actions",0),
            "baseline_present":bool(baseline),
            "financial_change":{}}
    for k,v in current.items():
        if k.endswith("_sar") and k in baseline:
            result["financial_change"][k]=round(float(v)-float(baseline[k]),2)
    print(json.dumps(result, indent=2))

if __name__ == "__main__": main(sys.argv[1])
