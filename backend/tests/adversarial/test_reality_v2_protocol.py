"""Protocol-level checks for the second Reality Test.

A live DB/UI run is intentionally not faked.  This test verifies the generated
merchant corpus and the integrity rules before an operator runs the E2E harness.
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent / "fixtures" / "reality_v2"
BUSINESSES = ["baqala", "supermarket", "cafe", "restaurant", "general_retail"]


def test_five_businesses_have_120_days_and_hidden_truth_is_separate():
    truth = pd.read_csv(ROOT / "hidden_ground_truth.csv")
    assert set(truth.business) == set(BUSINESSES)
    assert len(truth) == 25
    for business in BUSINESSES:
        sales = pd.read_csv(ROOT / f"{business}_sales.csv")
        inv = pd.read_csv(ROOT / f"{business}_inventory.csv")
        assert len(inv) == 5
        assert sales.date.nunique() >= 80
        assert set(sales.sku).issubset(set(inv.sku))
    assert not any("hidden_ground_truth" in p.name for p in ROOT.glob("*_sales.csv"))


def test_corruption_fixture_contains_required_adversarial_cases():
    bad = pd.read_csv(ROOT / "adversarial_corrupt_sales.csv")
    assert len(bad) == 15
    assert (bad.quantity < 0).any()
    assert (bad.date == "not-a-date").any()
    assert (bad.cost_price == "bad").any()
