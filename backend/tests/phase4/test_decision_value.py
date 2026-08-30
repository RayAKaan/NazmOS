from app.services.decision_value import DecisionComparison, classify_decision_value, summarize_decisions


def test_agreement_is_neutral():
    assert classify_decision_value("REORDER", "REORDER", "REORDER") == "NEUTRAL_OVERRIDE"


def test_good_override():
    assert classify_decision_value("DISCOUNT", "DO_NOTHING", "DO_NOTHING") == "GOOD_OVERRIDE"


def test_bad_override():
    assert classify_decision_value("REORDER", "DO_NOTHING", "REORDER") == "BAD_OVERRIDE"


def test_unknown_truth_is_unresolved():
    assert classify_decision_value("DISCOUNT", "DO_NOTHING", None) == "UNRESOLVED"


def test_summary_counts_ai_safety_metrics():
    rows = [
        DecisionComparison("1", "A", "B", "B", category="GOOD_OVERRIDE", ai_called=True, latency_ms=100),
        DecisionComparison("2", "A", "A", "A", category="NEUTRAL_OVERRIDE", ai_called=True),
        DecisionComparison("3", "A", "C", "A", category="BAD_OVERRIDE", ai_called=True, constraint_violation=True),
    ]
    result = summarize_decisions(rows)
    assert result["GOOD_OVERRIDE"] == 1
    assert result["BAD_OVERRIDE"] == 1
    assert result["NEUTRAL_OVERRIDE"] == 1
    assert result["ai_calls"] == 3
    assert result["constraint_violations"] == 1
