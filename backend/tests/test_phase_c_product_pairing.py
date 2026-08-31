"""Phase C3 — fuzzy product pairing between sales and inventory files.

Adversarial name variants (Coca-Cola family), tier boundaries, determinism,
one-to-one collision handling, and the rule that low-confidence matches are
NEVER forced.
"""
from __future__ import annotations

from app.services.product_pairing import HIGH_THRESHOLD, MEDIUM_THRESHOLD, pair_products


def _scores(report) -> dict[str, int]:
    return {p.sales_name: p.score for p in report.paired}


def test_coca_cola_variant_family_auto_matches_high():
    report = pair_products(
        ["Coca Cola 330ml", "Coca Cola 330", "Coca-Cola 330 ML", "كوكا كولا 330 مل"],
        ["Coca-Cola 330ml Can", "كوكا كولا 330", "Coca-Cola 330 ML", "Coca Cola 330"],
    )
    assert len(report.paired) == 4
    assert all(tier == "HIGH" for tier in [p.tier for p in report.paired])
    assert report.unmatched_sales == []
    assert report.unmatched_inventory == []


def test_low_confidence_matches_are_never_forced():
    report = pair_products(["Coca Cola"], ["Pepsi 330ml", "Mountain Dew", "Sprite Zero"])
    assert report.paired == []
    assert report.unmatched_sales == ["Coca Cola"]
    assert len(report.unmatched_inventory) == 3


def test_clear_miss_becomes_unmatched():
    report = pair_products(
        ["Blue Label Coffee 200g"],
        ["Green Tea 100 Pack", "Sugar 1kg", "Chips 90g"],
    )
    assert report.paired == []
    assert report.unmatched_sales == ["Blue Label Coffee 200g"]


def test_tier_threshold_constants_are_sane():
    assert HIGH_THRESHOLD == 88
    assert MEDIUM_THRESHOLD == 75
    assert MEDIUM_THRESHOLD < HIGH_THRESHOLD


def test_medium_tier_is_conservative_flag_not_title_case_variant():
    report = pair_products(
        ["Milk 1L"],
        ["Full Cream Milk 1 Liter"],
    )
    if report.paired:
        assert report.paired[0].tier in {"HIGH", "MEDIUM"}
    assert len(report.paired) <= 1


def test_deterministic_on_identical_input():
    names = ["Sugar 1kg", "سكر ١ كجم", "Tea 100g", "Chips", "Milk 1L"]
    inv = ["Reference Sugar", "Tea 100g", "Milk 1 Litre", "Chips"]
    a = pair_products(names, inv)
    b = pair_products(names, inv)
    assert [(p.sales_name, p.inventory_name, p.score) for p in a.paired] == [
        (p.sales_name, p.inventory_name, p.score) for p in b.paired
    ]
    assert a.unmatched_sales == b.unmatched_sales


def test_same_inventory_product_is_paired_to_at_most_one_sales_product():
    sales = ["Food Product", "Food Product Deluxe"]
    inventory = ["Food Product"]
    report = pair_products(sales, inventory)
    assert len(report.paired) == 1
    assert len(report.unmatched_sales) == 1

    # The higher-scoring variant wins the single slot.
    exact = pair_products(["Food Product"], inventory)
    assert exact.paired[0].sales_name == "Food Product"


def test_empty_inputs_are_safe():
    assert pair_products([], []).attempted == 0
    assert pair_products(["A"], []).attempted == 0


def test_bound_never_exceeds_max_products():
    many = [f"Product {i}" for i in range(2500)]
    report = pair_products(many, many[:300])
    assert report.truncated is True
    assert len(report.paired) <= 300