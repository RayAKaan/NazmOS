"""Unit tests for advanced Learning Engine helpers."""
import pytest

from app.services.learning_engine_advanced import (
    BetaDistribution,
    update_pricing_confidence,
    update_restock_confidence,
    graph_similarity,
    recommend_suppliers_by_similarity,
    assign_holdback_group,
    compare_groups,
)


def test_beta_mean():
    beta = BetaDistribution(alpha=8, beta=2)
    assert beta.mean() == 0.8


def test_update_pricing_confidence_accepted():
    prior = BetaDistribution(alpha=5, beta=5)
    updated = update_pricing_confidence(prior, True, revenue_impact_sar=5000)
    assert updated.alpha > prior.alpha
    assert updated.beta == prior.beta


def test_update_restock_confidence_avoided():
    prior = BetaDistribution(alpha=3, beta=7)
    updated = update_restock_confidence(prior, True, waste_reduction_sar=3000)
    assert updated.alpha > prior.alpha


def test_graph_similarity_identical():
    assert graph_similarity({"a", "b", "c"}, {"a", "b", "c"}) == 1.0


def test_recommend_suppliers_by_similarity():
    candidates = {
        "sup1": {"a", "b"},
        "sup2": {"c", "d"},
    }
    result = recommend_suppliers_by_similarity({"a", "b", "e"}, candidates, min_similarity=0.2)
    assert len(result) == 1
    assert result[0]["supplier_id"] == "sup1"


def test_assign_holdback_group_deterministic():
    g1 = assign_holdback_group("biz-1", "pro")
    g2 = assign_holdback_group("biz-1", "pro")
    assert g1 == g2
    assert g1 in {"control", "treatment"}


def test_compare_groups_significant():
    control = [100.0] * 30
    treatment = [110.0] * 30
    result = compare_groups(control, treatment)
    assert result["lift_pct"] == 10.0
    assert result["significant"] is True


def test_compare_groups_insufficient_data():
    result = compare_groups([100.0], [110.0])
    assert result["significant"] is False
