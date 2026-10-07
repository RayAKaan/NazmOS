"""Real deterministic analytics over canonical state (spec §29-§35).

The audit found four fabricated scores (``return 62``, ``return 69``, ``return 91``
in two files) and roughly fifteen zero-stubs in the domain analyzers. Those numbers
reached the merchant as if they were measurements, which is worse than showing
nothing.

The governing rule, applied to every function here:

    **no evidence → ``None``, never ``0.0``**

    Revenue with no cost evidence is *unknown*, not zero. A gross margin computed
    from missing cost is not 100% and is not 0% — it does not exist. Every figure
    below therefore carries its own coverage statement, so a consumer can always
    tell a computed value from an absent one.

Formulas are documented per function and are reproducible by hand from the events
and evidence ids returned alongside each result.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Mapping, Optional, Sequence

from app.services.orbit.contracts import (
    BusinessEvent,
    BusinessEventType,
    Conflict,
    Entity,
    EntityKind,
    EvidenceRegistry,
    FieldStatus,
    Measured,
)

TWO_PLACES = Decimal("0.01")


def _q(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Metric:
    """One computed figure with the evidence that supports it.

    ``value`` is ``None`` when the metric could not be computed. ``formula`` is
    included so any number on screen can be reproduced by hand.
    """

    name: str
    value: Optional[Decimal]
    unit: str = "count"
    formula: str = ""
    evidence_ids: tuple[str, ...] = ()
    #: How much of the relevant population the figure covers, 0..1. ``None`` means
    #: the metric was not computable at all.
    coverage: Optional[Decimal] = None
    limitation: str = ""
    #: Fields excluded because the evidence for them is missing.
    incomplete_because: tuple[str, ...] = ()

    @property
    def is_known(self) -> bool:
        return self.value is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": str(self.value) if self.value is not None else None,
            "unit": self.unit,
            "formula": self.formula,
            "evidence_ids": list(self.evidence_ids),
            "coverage": str(self.coverage) if self.coverage is not None else None,
            "limitation": self.limitation,
            "incomplete_because": list(self.incomplete_because),
            "is_known": self.is_known,
        }


def _sum(values: Iterable[Decimal]) -> Decimal:
    return sum(values, Decimal(0))


def _evidence_of(events: Sequence[BusinessEvent]) -> tuple[str, ...]:
    return tuple(sorted({eid for e in events for eid in e.evidence_ids}))


# ─────────────────────────────────────────────────────────────────────────────
# Margin (§32)
# ─────────────────────────────────────────────────────────────────────────────

def margin_metrics(events: Sequence[BusinessEvent]) -> dict[str, Metric]:
    """Sales, cost, gross profit and margin from canonical events.

    ``gross_profit`` requires *every* included sale to carry cost. If any sale
    lacks cost, gross profit and margin are reported unknown rather than computed
    from a partial total — a partial-cost profit understates the real figure and
    looks authoritative while doing so.
    """
    sales = [
        e for e in events
        if e.event_type is BusinessEventType.SALE and e.amount.value is not None
    ]
    evidence = _evidence_of(sales)

    revenue = _sum(e.amount.value for e in sales)
    # Cost comes from the event's own cost measurement, never from its sell price.
    # A dataset carrying only a sell price has no margin to report, and deriving
    # "cost" from ``unit_price`` would report margin as exactly zero — a confident,
    # plausible and completely fictional number.
    line_costs: list[Decimal] = []
    lines_without_cost = 0
    for event in sales:
        unit = event.cost.value
        qty = event.quantity.value
        if unit is None or qty is None:
            lines_without_cost += 1
            continue
        line_costs.append(unit * qty)

    total_lines = len(sales)
    cost_complete = total_lines > 0 and lines_without_cost == 0
    total_cost = _sum(line_costs) if cost_complete else None

    metrics: dict[str, Metric] = {
        "sales": Metric(
            name="sales",
            value=_q(revenue) if total_lines else None,
            unit="currency",
            formula="sum(sale.amount) over all sale events",
            evidence_ids=evidence,
            coverage=Decimal(1) if total_lines else None,
        ),
        "cost": Metric(
            name="cost",
            value=_q(total_cost) if cost_complete else None,
            unit="currency",
            formula="sum(unit_price * quantity) over sales where both are known",
            evidence_ids=evidence,
            coverage=(
                Decimal(len(line_costs)) / Decimal(total_lines) if total_lines else None
            ),
            incomplete_because=(
                (f"{lines_without_cost} of {total_lines} sales have no cost",)
                if lines_without_cost else ()
            ),
        ),
    }

    if cost_complete and total_lines:
        gross = revenue - total_cost
        metrics["gross_profit"] = Metric(
            name="gross_profit",
            value=_q(gross),
            unit="currency",
            formula="sales - cost",
            evidence_ids=evidence,
            coverage=Decimal(1),
        )
        metrics["gross_margin"] = Metric(
            name="gross_margin",
            value=_q(gross / revenue * 100) if revenue != 0 else None,
            unit="percent",
            formula="(sales - cost) / sales * 100",
            evidence_ids=evidence,
            coverage=Decimal(1),
            limitation="" if revenue != 0 else "sales total is zero, so margin is undefined",
        )
    else:
        reason = (
            f"{lines_without_cost} of {total_lines} sales lack cost evidence"
            if total_lines
            else "no sales events were observed"
        )
        for name in ("gross_profit", "gross_margin"):
            metrics[name] = Metric(
                name=name,
                value=None,
                unit="currency" if name == "gross_profit" else "percent",
                formula=(
                    "sales - cost" if name == "gross_profit"
                    else "(sales - cost) / sales * 100"
                ),
                evidence_ids=evidence,
                coverage=None,
                limitation=f"{reason}; this figure is unknown, not zero",
            )

    return metrics


def margin_by_product(
    events: Sequence[BusinessEvent],
) -> dict[str, dict[str, Metric]]:
    """Per-product margin, with the same unknown-not-zero rule."""
    grouped: dict[str, list[BusinessEvent]] = defaultdict(list)
    for event in events:
        if event.event_type is not BusinessEventType.SALE:
            continue
        product = event.entity_refs.get(EntityKind.PRODUCT.value)
        if product:
            grouped[product].append(event)
    return {product: margin_metrics(group) for product, group in sorted(grouped.items())}


def margin_erosion(events: Sequence[BusinessEvent]) -> Metric:
    """Change in margin between the first and last third of the observed period.

    A period with fewer than six dated sales cannot support a trend claim, so the
    metric is unknown rather than computed from three points.
    """
    dated = sorted(
        (e for e in events
         if e.event_type is BusinessEventType.SALE and e.business_local_date),
        key=lambda e: (e.business_local_date, e.event_id),
    )
    if len(dated) < 6:
        return Metric(
            name="margin_erosion",
            value=None,
            unit="percentage_points",
            formula="margin(last third) - margin(first third)",
            coverage=None,
            limitation=(
                f"only {len(dated)} dated sales available; at least 6 are needed to "
                "claim a trend"
            ),
        )

    third = len(dated) // 3
    early = margin_metrics(dated[:third])
    late = margin_metrics(dated[-third:])
    early_margin, late_margin = early.get("gross_margin"), late.get("gross_margin")
    if not early_margin or not late_margin or not early_margin.is_known or not late_margin.is_known:
        return Metric(
            name="margin_erosion",
            value=None,
            unit="percentage_points",
            formula="margin(last third) - margin(first third)",
            coverage=None,
            limitation="margin could not be computed for one of the two periods",
        )
    return Metric(
        name="margin_erosion",
        value=_q(late_margin.value - early_margin.value),
        unit="percentage_points",
        formula="margin(last third) - margin(first third)",
        evidence_ids=_evidence_of(dated),
        coverage=Decimal(1),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Inventory (§31)
# ─────────────────────────────────────────────────────────────────────────────

def inventory_metrics(events: Sequence[BusinessEvent]) -> dict[str, Metric]:
    """Real inventory arithmetic.

    Stock-on-hand is taken from the latest observation per product; movement is
    taken from sales. Where a balance cannot be reconciled the metric reports the
    components it *can* verify plus the reason it cannot close.
    """
    sales = [
        e for e in events
        if e.event_type is BusinessEventType.SALE and e.quantity.value is not None
    ]
    observations = [
        e for e in events
        if e.event_type is BusinessEventType.STOCK_OBSERVATION
        and e.quantity.value is not None
    ]
    evidence = _evidence_of(events)

    units_sold = _sum(e.quantity.value for e in sales)

    # Latest observation per product wins; earlier ones are history, not current.
    latest: dict[str, BusinessEvent] = {}
    for event in sorted(
        observations,
        key=lambda e: (e.business_local_date or date.min, e.event_time or date.min, e.event_id),
    ):
        product = event.entity_refs.get(EntityKind.PRODUCT.value)
        if product:
            latest[product] = event

    on_hand_total: Optional[Decimal] = (
        _sum(e.quantity.value for e in latest.values()) if latest else None
    )
    dated_observations = [e for e in observations if e.business_local_date]

    metrics: dict[str, Metric] = {
        "units_sold": Metric(
            name="units_sold",
            value=_q(units_sold) if sales else None,
            unit="count",
            formula="sum(sale.quantity) over all sale events",
            evidence_ids=_evidence_of(sales),
            coverage=Decimal(1) if sales else None,
        ),
        "stock_on_hand": Metric(
            name="stock_on_hand",
            value=_q(on_hand_total) if on_hand_total is not None else None,
            unit="count",
            formula="sum(latest stock observation per product)",
            evidence_ids=_evidence_of(observations),
            coverage=(
                Decimal(len(latest)) / Decimal(len({e.entity_refs.get(EntityKind.PRODUCT.value)
                                                    for e in observations} - {None}))
                if latest else None
            ),
            limitation=(
                "" if dated_observations else
                "stock observations carry no date, so this is an undated snapshot"
            ),
        ),
        "observed_products": Metric(
            name="observed_products",
            value=Decimal(len(latest)) if latest else None,
            unit="count",
            formula="count(distinct products with a stock observation)",
        ),
    }

    # Inventory value needs both a quantity and a unit cost.
    valued: list[Decimal] = []
    unvalued = 0
    for event in latest.values():
        unit_cost = event.cost.value
        qty = event.quantity.value
        if unit_cost is None or qty is None:
            unvalued += 1
            continue
        valued.append(unit_cost * qty)
    metrics["inventory_value"] = Metric(
        name="inventory_value",
        value=_q(_sum(valued)) if valued else None,
        unit="currency",
        formula="sum(unit_cost * quantity) over products with a stock observation",
        evidence_ids=_evidence_of(observations),
        coverage=(
            Decimal(len(valued)) / Decimal(len(latest)) if latest else None
        ),
        incomplete_because=(
            (f"{unvalued} of {len(latest)} products have no unit cost",) if unvalued else ()
        ),
    )

    # Negative stock is a data-quality signal, reported rather than clamped to 0.
    negative = [e for e in latest.values() if (e.quantity.value or 0) < 0]
    metrics["negative_stock_observations"] = Metric(
        name="negative_stock_observations",
        value=Decimal(len(negative)) if latest else None,
        unit="count",
        formula="count(products whose latest stock observation is below zero)",
        evidence_ids=_evidence_of([e for e in latest.values() if (e.quantity.value or 0) < 0]),
    )

    # Days of cover needs a rate over time, which needs a period.
    metrics["days_of_cover"] = _days_of_cover(events)
    return metrics


def _days_of_cover(events: Sequence[BusinessEvent]) -> Metric:
    """Average cover, or unknown when the observation window is too short."""
    sales = [
        e for e in events
        if e.event_type is BusinessEventType.SALE
        and e.quantity.value is not None
        and e.business_local_date
    ]
    stock = [
        e for e in events
        if e.event_type is BusinessEventType.STOCK_OBSERVATION
        and e.quantity.value is not None
        and e.business_local_date
    ]
    if not sales or not stock:
        return Metric(
            name="days_of_cover",
            value=None,
            unit="days",
            formula="stock_on_hand / average_daily_sales",
            coverage=None,
            limitation=(
                "days of cover needs both dated sales and dated stock observations; "
                f"sales={len(sales)}, stock={len(stock)}"
            ),
        )

    first = min(e.business_local_date for e in sales)
    last = max(e.business_local_date for e in sales)
    span_days = (last - first).days + 1
    if span_days < 1:
        return Metric(
            name="days_of_cover", value=None, unit="days",
            formula="stock_on_hand / average_daily_sales",
            coverage=None, limitation="the sales period covers less than one day",
        )

    daily_rate = _sum(e.quantity.value for e in sales) / Decimal(span_days)
    on_hand = _sum(e.quantity.value for e in stock)
    if daily_rate <= 0:
        return Metric(
            name="days_of_cover", value=None, unit="days",
            formula="stock_on_hand / average_daily_sales",
            coverage=None,
            limitation="no units were sold in the period, so cover is infinite, not zero",
        )
    return Metric(
        name="days_of_cover",
        value=_q(on_hand / daily_rate),
        unit="days",
        formula="stock_on_hand / (units_sold / period_days)",
        evidence_ids=_evidence_of(events),
        coverage=Decimal(1),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Procurement (§33) and expense (§34)
# ─────────────────────────────────────────────────────────────────────────────

def procurement_metrics(
    events: Sequence[BusinessEvent], entities: Sequence[Entity] = ()
) -> dict[str, Metric]:
    """Supplier count, purchase value and concentration from real evidence."""
    purchases = [
        e for e in events
        if e.event_type in (BusinessEventType.PURCHASE, BusinessEventType.PURCHASE_ORDER)
    ]
    suppliers = {
        e.canonical_name for e in entities
        if e.kind is EntityKind.SUPPLIER and e.canonical_name
    }
    evidence = _evidence_of(purchases)

    amounts = [e.amount.value for e in purchases if e.amount.value is not None]
    metrics: dict[str, Metric] = {
        "supplier_count": Metric(
            name="supplier_count",
            value=Decimal(len(suppliers)) if suppliers else None,
            unit="count",
            formula="count(distinct supplier entities)",
            evidence_ids=tuple(sorted(
                eid for e in events for eid in e.evidence_ids
            )),
        ),
        "purchase_events": Metric(
            name="purchase_events",
            value=Decimal(len(purchases)) if purchases else None,
            unit="count",
            formula="count(purchase and purchase_order events)",
            evidence_ids=evidence,
        ),
        "purchase_value": Metric(
            name="purchase_value",
            value=_q(_sum(amounts)) if amounts else None,
            unit="currency",
            formula="sum(purchase.amount)",
            evidence_ids=evidence,
            coverage=(
                Decimal(len(amounts)) / Decimal(len(purchases)) if purchases else None
            ),
        ),
    }

    # Concentration: share of purchase value from the largest supplier.
    per_supplier: dict[str, Decimal] = defaultdict(Decimal)
    for event in purchases:
        supplier = event.entity_refs.get(EntityKind.SUPPLIER.value)
        if supplier and event.amount.value is not None:
            per_supplier[supplier] += event.amount.value
    if per_supplier:
        total = _sum(per_supplier.values())
        top = max(per_supplier.values())
        metrics["supplier_concentration"] = Metric(
            name="supplier_concentration",
            value=_q(top / total * 100) if total != 0 else None,
            unit="percent",
            formula="largest supplier purchase value / total purchase value * 100",
            evidence_ids=evidence,
            coverage=(
                Decimal(len([e for e in purchases
                             if e.entity_refs.get(EntityKind.SUPPLIER.value)
                             and e.amount.value is not None]))
                / Decimal(len(purchases)) if purchases else None
            ),
        )
    else:
        metrics["supplier_concentration"] = Metric(
            name="supplier_concentration", value=None, unit="percent",
            formula="largest supplier purchase value / total purchase value * 100",
            coverage=None,
            limitation="no purchase event links a supplier to an amount",
        )

    metrics["lead_time_days"] = Metric(
        name="lead_time_days",
        value=None, unit="days",
        formula="mean(received_date - ordered_date) across purchase orders",
        coverage=None,
        limitation=(
            "lead time needs both an order date and a receipt date on the same "
            "purchase; neither is derived from a single dated row"
        ),
    )
    metrics["minimum_order_quantity"] = Metric(
        name="minimum_order_quantity",
        value=None, unit="count",
        formula="minimum quantity per purchase order per supplier",
        coverage=None,
        limitation="no supplier minimum-order policy is present in the evidence",
    )
    return metrics


def expense_metrics(events: Sequence[BusinessEvent]) -> dict[str, Metric]:
    """Expense totals from real expense and payment evidence."""
    expenses = [
        e for e in events
        if e.event_type in (BusinessEventType.EXPENSE, BusinessEventType.PAYMENT)
        and e.amount.value is not None
    ]
    expense_only = [e for e in expenses if e.event_type is BusinessEventType.EXPENSE]
    evidence = _evidence_of(expenses)

    total = _sum(e.amount.value for e in expenses)
    return {
        "total_expense": Metric(
            name="total_expense",
            value=_q(total) if expenses else None,
            unit="currency",
            formula="sum(amount) over expense and payment events",
            evidence_ids=evidence,
            coverage=Decimal(1) if expenses else None,
        ),
        "expense_transactions": Metric(
            name="expense_transactions",
            value=Decimal(len(expense_only)) if expense_only else None,
            unit="count",
            formula="count(expense events)",
            evidence_ids=_evidence_of(expense_only),
        ),
        "payment_transactions": Metric(
            name="payment_transactions",
            value=Decimal(
                len([e for e in expenses if e.event_type is BusinessEventType.PAYMENT])
            ) if expenses else None,
            unit="count",
            formula="count(payment events carrying an amount)",
            evidence_ids=_evidence_of(
                [e for e in expenses if e.event_type is BusinessEventType.PAYMENT]
            ),
            limitation=(
                "" if expense_only else
                "no event is typed as an expense, so payments and expenses cannot "
                "be separated; bank movements are not the same as operating expenses"
            ),
        ),
    }


def expense_by_category(events: Sequence[BusinessEvent]) -> dict[str, Metric]:
    """Expense totals grouped by the note/category carried on the event."""
    grouped: dict[str, list[BusinessEvent]] = defaultdict(list)
    for event in events:
        if event.event_type not in (BusinessEventType.EXPENSE, BusinessEventType.PAYMENT):
            continue
        if event.amount.value is None:
            continue
        key = event.external_reference or "uncategorised"
        grouped[key].append(event)
    return {
        category: Metric(
            name=category,
            value=_q(_sum(e.amount.value for e in group)),
            unit="currency",
            formula="sum(amount) over events in this category",
            evidence_ids=_evidence_of(group),
        )
        for category, group in sorted(grouped.items())
    }


# ─────────────────────────────────────────────────────────────────────────────
# Data quality (§35)
# ─────────────────────────────────────────────────────────────────────────────

def quality_score_from_dimensions(
    dimension_scores: Mapping[str, Optional[Decimal]],
    weights: Mapping[str, Decimal],
) -> Metric:
    """Reproducible quality score over the dimensions that could be evaluated.

    Unevaluated dimensions are excluded and the weight is renormalised, so an
    unknown dimension never drags the score down as though it were zero, and never
    lifts it as though it were perfect.
    """
    usable = {
        name: score for name, score in dimension_scores.items()
        if score is not None and weights.get(name, Decimal(0)) > 0
    }
    if not usable:
        return Metric(
            name="data_quality", value=None, unit="score",
            formula="weighted mean of evaluated dimensions",
            coverage=None,
            limitation="no quality dimension could be evaluated",
        )
    total_weight = _sum(weights[name] for name in usable)
    score = _sum(usable[name] * weights[name] for name in usable) / total_weight
    return Metric(
        name="data_quality",
        value=_q(score),
        unit="score",
        formula="sum(score_d * weight_d) / sum(weight_d) over evaluated dimensions",
        coverage=(
            total_weight / _sum(weights.values()) if weights else None
        ),
        incomplete_because=tuple(
            sorted(name for name, score in dimension_scores.items() if score is None)
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Aggregator
# ─────────────────────────────────────────────────────────────────────────────

def analyse(
    events: Sequence[BusinessEvent],
    entities: Sequence[Entity] = (),
    conflicts: Sequence[Conflict] = (),
    registry: Optional[EvidenceRegistry] = None,
) -> dict[str, Any]:
    """Every real metric, grouped by domain, with unknowns left unknown."""
    return {
        "margin": margin_metrics(events),
        "inventory": inventory_metrics(events),
        "procurement": procurement_metrics(events, entities),
        "expense": expense_metrics(events),
        "expense_by_category": expense_by_category(events),
        "margin_erosion": margin_erosion(events),
        "conflicts": {
            "total": Metric(
                name="conflicts",
                value=Decimal(len(conflicts)) if conflicts is not None else None,
                unit="count",
                formula="count(detected conflicts)",
            ),
        },
        "event_count": Metric(
            name="event_count",
            value=Decimal(len(events)) if events is not None else None,
            unit="count",
            formula="count(canonical events)",
        ),
    }


def unknown_metrics(report: Mapping[str, Any]) -> list[str]:
    """Every metric in a report that could not be computed.

    Surfaced deliberately: an analytics report that silently omits what it cannot
    compute looks complete.
    """
    out: list[str] = []

    def walk(node: Any, prefix: str = "") -> None:
        if isinstance(node, Metric):
            if not node.is_known:
                out.append(node.name)
        elif isinstance(node, Mapping):
            for key, value in node.items():
                walk(value, f"{prefix}.{key}" if prefix else str(key))

    walk(report)
    return sorted(set(out))
