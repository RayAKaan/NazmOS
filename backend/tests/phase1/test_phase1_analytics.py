"""Real analytics tests (spec §29-§35).

The audit found fabricated scores (``return 62``, ``return 69``, ``return 91`` and
a hardcoded ``91`` inside a weighted health formula) plus two invented money
figures (a 70%-of-sell-price cost estimate and ``quantity * 10``). Those reached
merchants looking like measurements.

These tests pin the replacement rule: a figure is either computed from evidence or
reported as unknown. Never zero, never a guess.
"""
from __future__ import annotations

import csv
import io
from decimal import Decimal
from uuid import uuid4

import pytest

from app.services.orbit.analytics import (
    Metric,
    analyse,
    expense_metrics,
    inventory_metrics,
    margin_erosion,
    margin_metrics,
    procurement_metrics,
    quality_score_from_dimensions,
    unknown_metrics,
)
from app.services.orbit.ingestion.pipeline import CanonicalOrbitIngestionPipeline

SELL_ONLY_HEADERS = ["Date", "Item", "SKU", "Qty", "Unit Price", "Amount", "Branch"]
SELL_ONLY_ROWS = [
    ["2026-03-01", "Pepsi 330ml", "P330", 12, "1.50 SAR", "18.00 SAR", "Riyadh"],
    ["2026-03-02", "Pepsi 500ml", "P500", 8, "1.80 SAR", "14.40 SAR", "Riyadh"],
]
WITH_COST_HEADERS = [
    "Date", "Item", "SKU", "Qty", "Unit Price", "Cost", "Amount", "Branch",
]
WITH_COST_ROWS = [
    ["2026-03-01", "Pepsi 330ml", "P330", 12, "1.50 SAR", "1.10 SAR", "18.00 SAR", "Riyadh"],
    ["2026-03-02", "Pepsi 500ml", "P500", 8, "1.80 SAR", "1.40 SAR", "14.40 SAR", "Riyadh"],
]
INVENTORY_HEADERS = ["SKU", "Item", "Current Stock", "Cost", "Unit", "Location"]
INVENTORY_ROWS = [
    ["P330", "Pepsi 330ml", 40, "1.10 SAR", "piece", "Riyadh"],
    ["P500", "Pepsi 500ml", 20, "1.40 SAR", "piece", "Riyadh"],
]


def to_csv(headers, rows) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


def _ingest(*artifacts):
    """Ingest (name, content) pairs through one shared pipeline."""
    pipeline = CanonicalOrbitIngestionPipeline(business_id=uuid4())
    result = None
    for name, content in artifacts:
        result = pipeline.ingest(content, source_name=name)
    assert result is not None
    return result


class TestNoFabricatedScores:
    """The specific constants the audit found must not come back."""

    FORBIDDEN = ("return 62", "return 69", "return 91", "91 * 0.10",
                 "quantity * 10", "* 0.7  # estimate cost")

    def _sources(self) -> list[str]:
        from pathlib import Path

        import app.services as services_root

        root = Path(services_root.__file__).resolve().parent
        targets = [
            root / "orbit_financial_xray.py",
            root / "audit_persistence.py",
            root / "nazm_planner.py",
            root / "orbit_domains" / "health.py",
            root / "orbit_domains" / "inventory.py",
            root / "orbit_domains" / "margin.py",
            root / "orbit_domains" / "procurement.py",
            root / "orbit_domains" / "expense.py",
        ]
        return [p.read_text(encoding="utf-8") for p in targets if p.exists()]

    def test_no_hardcoded_scores_remain(self):
        for source in self._sources():
            for needle in self.FORBIDDEN:
                # A comment explaining the removal is fine; executable code is not.
                for line in source.splitlines():
                    if needle in line and not line.strip().startswith(
                        ("#", "*", '"""', "Previously", "The previous", "four competing")
                    ):
                        pytest.fail(f"fabricated value {needle!r} still in production code")


class TestMargin:
    def test_sales_are_summed_from_evidence(self):
        result = _ingest(("pos.csv", to_csv(SELL_ONLY_HEADERS, SELL_ONLY_ROWS)))
        metrics = margin_metrics(result.events)
        assert metrics["sales"].value == Decimal("32.40")
        assert metrics["sales"].formula

    def test_missing_cost_yields_unknown_not_zero(self):
        """A sell price is not a cost. Margin without cost is unknown."""
        result = _ingest(("pos.csv", to_csv(SELL_ONLY_HEADERS, SELL_ONLY_ROWS)))
        metrics = margin_metrics(result.events)
        assert metrics["cost"].value is None
        assert metrics["gross_profit"].value is None
        assert metrics["gross_margin"].value is None
        assert "unknown, not zero" in metrics["gross_profit"].limitation

    def test_cost_is_never_derived_from_the_sell_price(self):
        """The specific bug: unit_price used as cost yields margin 0.00."""
        result = _ingest(("pos.csv", to_csv(SELL_ONLY_HEADERS, SELL_ONLY_ROWS)))
        metrics = margin_metrics(result.events)
        assert metrics["gross_margin"].value != Decimal("0.00")

    def test_real_cost_produces_real_margin(self):
        result = _ingest(("pos.csv", to_csv(WITH_COST_HEADERS, WITH_COST_ROWS)))
        metrics = margin_metrics(result.events)
        assert metrics["cost"].value == Decimal("24.40")
        assert metrics["gross_profit"].value == Decimal("8.00")
        assert metrics["gross_margin"].value == Decimal("24.69")

    def test_partial_cost_does_not_produce_a_partial_profit(self):
        rows = [WITH_COST_ROWS[0], [
            "2026-03-02", "Pepsi 500ml", "P500", 8, "1.80 SAR", "", "14.40 SAR", "Riyadh",
        ]]
        result = _ingest(("pos.csv", to_csv(WITH_COST_HEADERS, rows)))
        metrics = margin_metrics(result.events)
        # Half the cost is worse than none: a partial-cost profit understates.
        assert metrics["gross_profit"].value is None
        assert metrics["cost"].incomplete_because

    def test_no_sales_means_no_figures(self):
        result = _ingest(("pos.csv", to_csv(SELL_ONLY_HEADERS, [])))
        metrics = margin_metrics(result.events)
        assert metrics["sales"].value is None
        assert metrics["gross_margin"].value is None

    def test_margin_erosion_needs_enough_dated_sales(self):
        result = _ingest(("pos.csv", to_csv(SELL_ONLY_HEADERS, SELL_ONLY_ROWS)))
        erosion = margin_erosion(result.events)
        assert erosion.value is None
        assert "at least 6" in erosion.limitation


class TestInventory:
    def test_stock_observations_are_valued_with_real_cost(self):
        result = _ingest(
            ("pos.csv", to_csv(WITH_COST_HEADERS, WITH_COST_ROWS)),
            ("inv.csv", to_csv(INVENTORY_HEADERS, INVENTORY_ROWS)),
        )
        metrics = inventory_metrics(result.events)
        assert metrics["stock_on_hand"].value == Decimal("60.00")
        assert metrics["inventory_value"].value == Decimal("72.00")

    def test_days_of_cover_is_unknown_without_dated_stock(self):
        result = _ingest(
            ("pos.csv", to_csv(WITH_COST_HEADERS, WITH_COST_ROWS)),
            ("inv.csv", to_csv(INVENTORY_HEADERS, INVENTORY_ROWS)),
        )
        metrics = inventory_metrics(result.events)
        assert metrics["days_of_cover"].value is None
        assert "dated" in metrics["days_of_cover"].limitation

    def test_units_sold_is_real(self):
        result = _ingest(("pos.csv", to_csv(SELL_ONLY_HEADERS, SELL_ONLY_ROWS)))
        metrics = inventory_metrics(result.events)
        assert metrics["units_sold"].value == Decimal("20.00")


class TestProcurementAndExpense:
    def test_procurement_without_purchases_is_unknown(self):
        result = _ingest(("pos.csv", to_csv(SELL_ONLY_HEADERS, SELL_ONLY_ROWS)))
        metrics = procurement_metrics(result.events, result.entities)
        assert metrics["purchase_value"].value is None
        assert metrics["purchase_events"].value is None

    def test_lead_time_is_declared_unavailable_rather_than_zero(self):
        result = _ingest(("pos.csv", to_csv(SELL_ONLY_HEADERS, SELL_ONLY_ROWS)))
        metrics = procurement_metrics(result.events, result.entities)
        assert metrics["lead_time_days"].value is None
        assert metrics["lead_time_days"].limitation

    def test_expense_without_expenses_is_unknown(self):
        result = _ingest(("pos.csv", to_csv(SELL_ONLY_HEADERS, SELL_ONLY_ROWS)))
        metrics = expense_metrics(result.events)
        assert metrics["total_expense"].value is None
        assert metrics["expense_transactions"].value is None

    def test_payments_are_not_called_expenses(self):
        """A bank movement is not an operating expense; the metric says so."""
        bank = to_csv(
            ["Date", "Description", "Amount", "Balance"],
            [["2026-03-05", "POS settlement", "500.00 SAR", "1200.00 SAR"]],
        )
        result = _ingest(("bank.csv", bank))
        metrics = expense_metrics(result.events)
        assert metrics["payment_transactions"].value == Decimal("1.00")
        assert metrics["expense_transactions"].value is None
        assert "cannot be separated" in metrics["payment_transactions"].limitation


class TestQualityScore:
    def test_score_is_reproducible_from_dimensions(self):
        scores = {"completeness": Decimal("0.8"), "validity": Decimal("0.6")}
        weights = {"completeness": Decimal("0.5"), "validity": Decimal("0.5")}
        metric = quality_score_from_dimensions(scores, weights)
        assert metric.value == Decimal("0.70")

    def test_unevaluated_dimensions_do_not_drag_the_score_down(self):
        """An unknown dimension is excluded, not counted as zero."""
        scores = {"completeness": Decimal("1.0"), "validity": None}
        weights = {"completeness": Decimal("0.5"), "validity": Decimal("0.5")}
        metric = quality_score_from_dimensions(scores, weights)
        assert metric.value == Decimal("1.00")
        assert "validity" in metric.incomplete_because

    def test_nothing_evaluable_yields_no_score(self):
        metric = quality_score_from_dimensions({}, {})
        assert metric.value is None


class TestReportIntegrity:
    def test_unknown_metrics_are_surfaced(self):
        result = _ingest(("pos.csv", to_csv(SELL_ONLY_HEADERS, SELL_ONLY_ROWS)))
        report = analyse(result.events, result.entities, result.conflicts)
        unknown = unknown_metrics(report)
        # A report that silently omitted them would look complete.
        assert "gross_profit" in unknown
        assert "purchase_value" in unknown

    def test_every_metric_states_its_formula(self):
        result = _ingest(("pos.csv", to_csv(WITH_COST_HEADERS, WITH_COST_ROWS)))
        report = analyse(result.events, result.entities, result.conflicts)
        for group in ("margin", "inventory", "procurement", "expense"):
            for name, metric in report[group].items():
                assert metric.formula, f"{group}.{name} has no formula"

    def test_known_metrics_carry_evidence(self):
        result = _ingest(("pos.csv", to_csv(WITH_COST_HEADERS, WITH_COST_ROWS)))
        report = analyse(result.events, result.entities, result.conflicts)
        assert report["margin"]["sales"].evidence_ids

    def test_metrics_are_json_shaped(self):
        result = _ingest(("pos.csv", to_csv(SELL_ONLY_HEADERS, SELL_ONLY_ROWS)))
        payload = margin_metrics(result.events)["sales"].to_dict()
        assert payload["is_known"] is True
        assert isinstance(payload["value"], str)
        assert "coverage" in payload