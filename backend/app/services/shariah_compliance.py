"""
NazmOS Shariah retail guardrails.

Core product scope:
- Halal/prohibited keyword screening for inventory imports/manual checks
- Anti-Ihtikar pricing ethics warnings for essential staples

Formal certification and regulated services are intentionally outside
NazmOS core Retail Recovery.
"""
import logging
from decimal import Decimal
from typing import Dict, Any, List

from app.utils.money import sar, decimal_value

logger = logging.getLogger("shariah_compliance")

PROHIBITED_KEYWORDS = [
    "pork", "khinzir", "خنزير", "لحم خنزير",
    "alcohol", "wine", "beer", "vodka", "whiskey", "khamr", "خمر", "كحول", "نبيذ",
    "lottery", "gambling", "maysir", "قمار", "ميسر",
    "gelatin (non-halal)", "lard",
]

ESSENTIAL_STAPLES = [
    "water", "ماء", "مياه",
    "milk", "حليب", "لبن",
    "bread", "خبز",
    "dates", "تمر", "تمور", "سكري", "خلاص",
    "flour", "دقيق", "طحين",
    "infant formula", "حليب أطفال",
]


def audit_inventory_halal_status(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Scan retail inventory items against prohibited categories."""
    flagged_items = []
    clean_count = 0

    for item in items:
        name = str(item.get("name", "")).lower()
        desc = str(item.get("description", "")).lower()
        sku = str(item.get("sku", ""))

        violation = None
        for kw in PROHIBITED_KEYWORDS:
            if kw in name or kw in desc:
                violation = {
                    "sku": sku,
                    "name": item.get("name"),
                    "violation": f"Contains prohibited keyword: '{kw}'",
                    "ruling": "Review required / prohibited retail category",
                }
                break

        if violation:
            flagged_items.append(violation)
        else:
            clean_count += 1

    status = "CLEAN_RETAIL_GUARDRAILS_PASSED" if not flagged_items else "REVIEW_REQUIRED_PROHIBITED_KEYWORD"
    return {
        "status": status,
        "total_items_scanned": len(items),
        "clean_items": clean_count,
        "flagged_violations": flagged_items,
        "audit_standard": "NazmOS Retail Guardrails",
    }


def screen_item_for_shariah(name: str, description: str = "", sku: str = "") -> Dict[str, Any]:
    result = audit_inventory_halal_status([{"name": name, "description": description, "sku": sku}])
    flags = result.get("flagged_violations", [])
    return {
        "shariah_status": "flagged_review_required" if flags else "halal_guard_passed",
        "shariah_flags": flags,
        "blocked": bool(flags),
    }


def check_pricing_ethics_ihtikar(
    item_name: str,
    old_price: float,
    new_price: float,
    cost_increase_pct: float = 0.0,
    is_ramadan: bool = False,
) -> Dict[str, Any]:
    """Warn against unjustified price hikes on essential staples."""
    name_lower = item_name.lower()
    is_essential = any(s in name_lower for s in ESSENTIAL_STAPLES)

    old_price_dec = sar(old_price)
    new_price_dec = sar(new_price)
    cost_increase_dec = decimal_value(cost_increase_pct)
    if old_price_dec <= 0:
        return {"ethical_status": "APPROVED", "note": "New item pricing."}

    price_increase_pct = ((new_price_dec - old_price_dec) / old_price_dec) * Decimal("100.0")
    unjustified_hike = price_increase_pct - cost_increase_dec
    threshold_pct = Decimal("10.0") if is_ramadan else Decimal("20.0")

    if is_essential and unjustified_hike > threshold_pct:
        return {
            "ethical_status": "FLAGGED_IHTIKAR_RISK",
            "item_name": item_name,
            "price_increase_pct": round(float(price_increase_pct), 2),
            "ruling": (
                f"'{item_name}' is an essential staple. Retail price increased by "
                f"{float(price_increase_pct):.1f}% while cost increased by {float(cost_increase_dec):.1f}%, "
                f"above the ethical threshold of {float(threshold_pct):.1f}%."
            ),
            "recommendation": "Cap retail margin increase to match wholesale cost inflation.",
        }

    return {
        "ethical_status": "APPROVED_ETHICAL_FAIR_TRADE",
        "item_name": item_name,
        "price_increase_pct": round(float(price_increase_pct), 2),
        "note": "Pricing aligns with fair trade guardrails.",
    }
