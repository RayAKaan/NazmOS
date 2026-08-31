"""Fuzzy product-name pairing between a sales file and an inventory file.

Uses rapidfuzz only. Tiers:
- HIGH   (>=88): confident automatic match
- MEDIUM (>=75): conservative match, flagged for review, still paired
- LOW    (<75):  not matched (counted as unmatched)

Never forces a low-confidence pairing. Deterministic and bounded so it is safe
for a public, unauthenticated endpoint.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from app.services.file_ingestion import normalize_text

HIGH_THRESHOLD = 88
MEDIUM_THRESHOLD = 75
MAX_PRODUCTS_PER_FILE = 2000  # C7 bound: never pair more than this many products
CANDIDATES_PER_NAME = 5  # top candidates per name; bounded, deterministic


@dataclass
class PairedProduct:
    sales_name: str
    inventory_name: str
    score: int
    tier: str  # HIGH | MEDIUM


@dataclass
class PairingReport:
    paired: list[PairedProduct] = field(default_factory=list)
    unmatched_sales: list[str] = field(default_factory=list)
    unmatched_inventory: list[str] = field(default_factory=list)
    truncated: bool = False

    @property
    def attempted(self) -> int:
        return len(self.paired) + len(self.unmatched_sales)

    @property
    def success_rate(self) -> float:
        if self.attempted == 0:
            return 0.0
        return round(100 * len(self.paired) / self.attempted, 1)


def _dedupe_keep_order(names: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        key = normalize_text(name)
        if key and key not in seen:
            seen.add(key)
            out.append(name)
    return out


def pair_products(sales_names: list[str], inventory_names: list[str]) -> PairingReport:
    """Pair sales products to inventory products by normalized fuzzy name."""
    sales = _dedupe_keep_order(sales_names)
    inventory = _dedupe_keep_order(inventory_names)
    if not sales or not inventory:
        return PairingReport()

    truncated = len(sales) > MAX_PRODUCTS_PER_FILE or len(inventory) > MAX_PRODUCTS_PER_FILE
    sales = sales[:MAX_PRODUCTS_PER_FILE]
    inventory = inventory[:MAX_PRODUCTS_PER_FILE]

    norm_sales = [normalize_text(n) for n in sales]
    norm_inventory = [normalize_text(n) for n in inventory]

    candidates: list[tuple[int, int, int]] = []
    for i, s in enumerate(norm_sales):
        matches = process.extract(
            s,
            norm_inventory,
            scorer=fuzz.WRatio,
            score_cutoff=MEDIUM_THRESHOLD,
            limit=CANDIDATES_PER_NAME,
        )
        for _name, score, inv_idx in matches:
            candidates.append((i, inv_idx, int(score)))

    # Greedy unique assignment: highest score first, each inventory name used
    # at most once. Ties broken by order (deterministic).
    candidates.sort(key=lambda c: (-c[2], c[0], c[1]))
    used_inventory: set[int] = set()
    assigned_sales: dict[int, tuple[int, int]] = {}
    for sales_idx, inv_idx, score in candidates:
        if sales_idx in assigned_sales or inv_idx in used_inventory:
            continue
        assigned_sales[sales_idx] = (inv_idx, score)
        used_inventory.add(inv_idx)

    paired: list[PairedProduct] = []
    for sales_idx, (inv_idx, score) in assigned_sales.items():
        tier = "HIGH" if score >= HIGH_THRESHOLD else "MEDIUM"
        paired.append(PairedProduct(sales[sales_idx], inventory[inv_idx], score, tier))
    paired.sort(key=lambda p: (-p.score, p.sales_name))

    unmatched_sales = [sales[i] for i in range(len(sales)) if i not in assigned_sales]
    unmatched_inventory = [inventory[i] for i in range(len(inventory)) if i not in used_inventory]

    return PairingReport(paired=paired, unmatched_sales=unmatched_sales, unmatched_inventory=unmatched_inventory, truncated=truncated)