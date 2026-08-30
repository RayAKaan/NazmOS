"""WS3 — financial vocabulary normalization (FINANCIAL_VOCABULARY_ADR.md).

Verifies the canonical key set, the alias map (every documented drift name
maps to a canonical key), and canonicalize() in-place rewrite semantics.
Also proves FinancialEstimate exposes the canonical _sar aliases without
changing its serialized form (properties are excluded from asdict()).
"""
from dataclasses import asdict

from app.services.financial_vocabulary import (
    ALIAS_MAP,
    CANONICAL_KEYS,
    EXPECTED_RECOVERY_SAR,
    RECOVERABLE_HIGH_SAR,
    RECOVERABLE_LOW_SAR,
    canonical_key,
    canonicalize,
)
from app.services.recovery_intelligence import FinancialEstimate


def test_canonical_keys_are_sar_suffixed():
    assert RECOVERABLE_LOW_SAR.endswith("_sar")
    assert RECOVERABLE_HIGH_SAR.endswith("_sar")
    assert EXPECTED_RECOVERY_SAR.endswith("_sar")
    assert all(k.endswith("_sar") for k in CANONICAL_KEYS)


def test_alias_map_points_only_at_canonical_keys():
    for alias, target in ALIAS_MAP.items():
        assert target in CANONICAL_KEYS, f"{alias} -> {target} is not canonical"
        assert alias != target, f"{alias} should not alias itself"


def test_known_drift_aliases_resolve_to_canonical():
    assert canonical_key("recoverable_low") == RECOVERABLE_LOW_SAR
    assert canonical_key("recoverable_value_low_sar") == RECOVERABLE_LOW_SAR
    assert canonical_key("recoverable_value_high_sar") == RECOVERABLE_HIGH_SAR
    assert canonical_key("expected_recovery") == EXPECTED_RECOVERY_SAR
    assert canonical_key("expected_recovery_sar_v2") == EXPECTED_RECOVERY_SAR


def test_canonicalize_normalizes_aliases_in_place():
    data = {
        "recoverable_value_low_sar": 1.0,
        "recoverable_high": 2.0,
        "expected_recovery_sar_v2": 3.0,
        "title": "kept",
    }
    canonicalize(data)
    assert data[RECOVERABLE_LOW_SAR] == 1.0
    assert data[RECOVERABLE_HIGH_SAR] == 2.0
    assert data[EXPECTED_RECOVERY_SAR] == 3.0
    assert data["title"] == "kept"
    assert "recoverable_value_low_sar" not in data
    assert "recoverable_high" not in data
    assert "expected_recovery_sar_v2" not in data


def test_canonicalize_keeps_explicit_canonical_over_alias():
    data = {"recoverable_low_sar": 9.0, "recoverable_value_low_sar": 1.0}
    canonicalize(data)
    assert data[RECOVERABLE_LOW_SAR] == 9.0, "canonical key must win over alias"


def test_canonicalize_does_not_mangle_unknown_keys():
    data = {"total_recoverable_sar": 5.0, "foo": "bar"}
    canonicalize(data)
    assert data == {"total_recoverable_sar": 5.0, "foo": "bar"}


def test_financial_estimate_exposes_sar_aliases():
    est = FinancialEstimate(
        inventory_value=100,
        capital_at_risk=80,
        recoverable_low=10,
        recoverable_high=50,
        expected_recovery=30,
    )
    assert est.recoverable_low_sar == 10
    assert est.recoverable_high_sar == 50
    assert est.expected_recovery_sar == 30
    assert est.capital_at_risk_sar == 80


def test_financial_estimate_json_unchanged_by_aliases():
    est = FinancialEstimate(recoverable_low=10, recoverable_high=50)
    serialized = est.json()
    assert "recoverable_low" in serialized
    assert "recoverable_low_sar" not in serialized
    assert set(asdict(est).keys()) == set(serialized.keys())