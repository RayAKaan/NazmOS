"""Canonical purchase-order / confirmed-inbound service (Phase 1).

Single source of truth for "how much stock is already committed to arrive" from
a tenant's open purchase orders. Used to make the deterministic reorder engine
PO-aware so it never over-orders against stock that is already on its way, and
never reorders against a ghost / cancelled / draft / already-received PO.

Phase 1 additions (Time-aware reasoning, Section 4 / A6 / A7):

* **Partial receipt** — `purchase_orders.received_items_json` (JSON keyed by
  item_id -> received_qty) lets the service subtract already-received quantity
  and count ONLY the remaining (``qty - received``) as still-expected inbound
  for a partially-received PO.
* **Arrival-window reasoning** — the service returns per-PO arrival dates and
  a time-aware reducer ``usable_confirmed_inbound`` that classifies inbound as
  *usable* (arrives strictly BEFORE the projected stockout date) vs *late*
  (arrives at/after stockout, or unknown). Callers use ``usable_qty`` to decide
  whether a reorder is genuinely actionable, so a far-future PO can no longer
  suppress a reorder needed today.

Data-model note: `purchase_orders.status` is a plain string column; `items_json`
is ``[{item_id, qty, unit_cost}]`` keyed by **item_id** (the item UUID as text).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.clock import utcnow

# ---------------------------------------------------------------------------
# Canonical PO status vocabulary (purchase_orders.status plain-string column)
# ---------------------------------------------------------------------------
PO_STATUS_DRAFT = "draft"
PO_STATUS_PENDING_APPROVAL = "pending_approval"
PO_STATUS_SENT = "sent"
PO_STATUS_APPROVED = "approved"
PO_STATUS_CONFIRMED = "confirmed"
PO_STATUS_RECEIVED = "received"
PO_STATUS_CANCELLED = "cancelled"

# Statuses that represent a FIRM commitment of goods still expected to arrive.
# These suppress reorder. `received` is intentionally excluded: its goods are
# already on the shelf (reflected in current_stock) so counting them again here
# would double-count inbound. `draft` is not yet committed; `cancelled` is void.
CONFIRMED_BOOKED_STATUSES = (
    PO_STATUS_APPROVED,
    PO_STATUS_SENT,
    PO_STATUS_CONFIRMED,
    PO_STATUS_PENDING_APPROVAL,
)

_GHOST_LIKE_STATUSES = (PO_STATUS_DRAFT, PO_STATUS_CANCELLED, PO_STATUS_RECEIVED)


def _money(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def po_classify_status(status: Optional[str]) -> str:
    """Classify a PO status into a stable canonical bucket.

    Buckets: ``confirmed`` (firm inbound), ``received``, ``cancelled``,
    ``draft``, ``unknown``. Tests and callers should assert against these
    buckets, not the raw string, so the plain-string status cannot drift.
    """
    s = (status or "").strip().lower()
    if s == PO_STATUS_RECEIVED:
        return "received"
    if s == PO_STATUS_CANCELLED:
        return "cancelled"
    if s == PO_STATUS_DRAFT:
        return "draft"
    if s in CONFIRMED_BOOKED_STATUSES:
        return "confirmed"
    return "unknown"


def is_open_inbound_status(status: Optional[str]) -> bool:
    """True if a PO status still represents goods committed to arrive."""
    return po_classify_status(status) == "confirmed"


@dataclass
class ConfirmedInbound:
    """Aggregated confirmed-inbound result for one item (or a whole business).

    ``confirmed_inbound_qty`` is the total committed-but-not-received quantity
    across all open POs (for partial receipts this is already reduced to the
    remaining quantity). Arrival metadata lets callers reason about WHEN stock
    arrives, not just how much is on paper.
    """

    item_id: str | None
    confirmed_inbound_qty: Decimal = Decimal("0")
    po_count: int = 0
    overdue_po_count: int = 0
    ghost_po_risk: bool = False
    earliest_arrival: date | None = None
    latest_arrival: date | None = None
    source_po_ids: list[str] = field(default_factory=list)
    line_items: list[dict] = field(default_factory=list)
    # Arrival-weekly breakdown keyed by expected arrival date (ISO str) -> qty.
    # A line with no expected_delivery is keyed under "unknown".
    arrivals_by_date: dict[str, Decimal] = field(default_factory=dict)

    @property
    def unknown_arrival_qty(self) -> Decimal:
        """Committed inbound with no usable expected-delivery date."""
        return self.arrivals_by_date.get("unknown", Decimal("0"))

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "confirmed_inbound_qty": float(self.confirmed_inbound_qty),
            "po_count": self.po_count,
            "overdue_po_count": self.overdue_po_count,
            "ghost_po_risk": self.ghost_po_risk,
            "earliest_arrival": self.earliest_arrival.isoformat() if self.earliest_arrival else None,
            "latest_arrival": self.latest_arrival.isoformat() if self.latest_arrival else None,
            "source_po_ids": self.source_po_ids,
            "confidence": "confirmed",
            "line_items": self.line_items,
            "arrivals_by_date": {
                k: float(v) for k, v in self.arrivals_by_date.items()
            },
        }


def _extract_qty(elem: Any, item_id: str | None) -> Decimal:
    """Qty of a PO line for the target item (0 if not matching)."""
    line_item_id = elem.get("item_id")
    if line_item_id is None:
        return Decimal("0")
    if item_id is not None and str(line_item_id) != str(item_id):
        return Decimal("0")
    return _money(elem.get("qty"))


def _parse_received_map(raw: Any) -> dict[str, Decimal]:
    """Parse received_items_json ({item_id: received_qty}) into a decimal map."""
    if isinstance(raw, dict):
        data = raw
    else:
        try:
            data = json.loads(raw) if raw else {}
        except Exception:
            data = {}
    out: dict[str, Decimal] = {}
    for k, v in (data or {}).items():
        if v is not None:
            try:
                out[str(k)] = Decimal(str(v))
            except Exception:
                continue
    return out


def _remaining_for(items: list[Any], item_id: str, received_map: dict[str, Decimal]) -> Decimal:
    """Remaining (`qty - received`) committed quantity for a line item.

    For a partially-received PO this is the only quantity that may count as
    still-expected inbound.
    """
    received = received_map.get(str(item_id), Decimal("0"))
    qty = Decimal("0")
    for elem in items:
        if not isinstance(elem, dict):
            continue
        if str(elem.get("item_id")) == str(item_id):
            qty = _money(elem.get("qty"))
            break
    return max(Decimal("0"), qty - received)


async def get_confirmed_inbound_map(
    db: AsyncSession,
    *,
    business_id: str | UUID,
    as_of: date | None = None,
    ghost_days: int = 30,
) -> dict[str, ConfirmedInbound]:
    """Return every item's confirmed inbound in ONE tenant-scoped query.

    Keys are item UUID strings (matching the ``item_id`` key used inside
    ``purchase_orders.items_json``). Each value is a ``ConfirmedInbound`` whose
    ``confirmed_inbound_qty`` is that item's committed-but-not-received quantity
    (reduced to remaining for partial receipts).
    """
    as_of = as_of or utcnow().date()
    status_values = ",".join(f"'{s}'" for s in CONFIRMED_BOOKED_STATUSES)
    rows = await db.execute(
        text(
            "SELECT po.id, po.po_number, po.status, po.expected_delivery, "
            "po.items_json, po.received_items_json "
            "FROM purchase_orders po "
            "WHERE po.business_id = :business_id "
            f"AND po.status IN ({status_values})"
        ),
        {"business_id": str(business_id)},
    )

    per_item: dict[str, ConfirmedInbound] = {}
    for po in rows.fetchall():
        try:
            items = po.items_json if isinstance(po.items_json, list) else json.loads(po.items_json or "[]")
        except Exception:
            items = []
        if not isinstance(items, list):
            items = []
        received_map = _parse_received_map(po.received_items_json)
        overdue = po.expected_delivery is not None and po.expected_delivery < as_of
        is_ghost = bool(
            overdue
            and po.expected_delivery is not None
            and (as_of - po.expected_delivery).days >= ghost_days
        )
        for elem in items:
            if not isinstance(elem, dict) or elem.get("item_id") is None:
                continue
            iid = str(elem.get("item_id"))
            remaining = _remaining_for(items, iid, received_map)
            if remaining <= 0:
                continue  # fully received line -> nothing still expected
            entry = per_item.setdefault(iid, ConfirmedInbound(item_id=iid))
            arrival = po.expected_delivery
            bucket = arrival.isoformat() if arrival else "unknown"
            entry.confirmed_inbound_qty += remaining
            entry.arrivals_by_date[bucket] = entry.arrivals_by_date.get(bucket, Decimal("0")) + remaining
            entry.po_count += 1
            if overdue:
                entry.overdue_po_count += 1
            if is_ghost:
                entry.ghost_po_risk = True
            if arrival is not None:
                entry.earliest_arrival = (
                    min(entry.earliest_arrival, arrival) if entry.earliest_arrival else arrival
                )
                entry.latest_arrival = (
                    max(entry.latest_arrival, arrival) if entry.latest_arrival else arrival
                )
            if str(po.id) not in entry.source_po_ids:
                entry.source_po_ids.append(str(po.id))
            entry.line_items.append(
                {
                    "po_id": str(po.id),
                    "po_number": po.po_number,
                    "status": po.status,
                    "expected_delivery": arrival.isoformat() if arrival else None,
                    "committed_qty": float(remaining),
                    "overdue": overdue,
                    "item_id": iid,
                }
            )

    for entry in per_item.values():
        entry.confirmed_inbound_qty = max(Decimal("0"), entry.confirmed_inbound_qty).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    return per_item


async def get_confirmed_inbound(
    db: AsyncSession,
    *,
    business_id: str | UUID,
    item_id: str | UUID | None = None,
    as_of: date | None = None,
    horizon_days: int = 14,
    ghost_days: int = 30,
) -> ConfirmedInbound | None:
    """Return confirmed inbound for a single item as of a date.

    Canonical, tenant-scoped, virtual-clock aware (defaults to ``utcnow()``).
    Counts only firm open POs (approved/sent/confirmed/pending_approval) and
    only the remaining quantity for partially-received lines. An overdue open PO
    (past ``expected_delivery``) still suppresses reorder but is surfaced via
    ``overdue_po_count`` and ``ghost_po_risk`` so callers can avoid letting a
    stale object block recovery forever.
    """
    as_of = as_of or utcnow().date()
    if item_id is None:
        agg = ConfirmedInbound(item_id=None)
        m = await get_confirmed_inbound_map(db, business_id=business_id, as_of=as_of, ghost_days=ghost_days)
        for entry in m.values():
            agg.confirmed_inbound_qty += entry.confirmed_inbound_qty
            agg.po_count += entry.po_count
            agg.overdue_po_count += entry.overdue_po_count
            agg.ghost_po_risk = agg.ghost_po_risk or entry.ghost_po_risk
            agg.line_items.extend(entry.line_items)
            for k, v in entry.arrivals_by_date.items():
                agg.arrivals_by_date[k] = agg.arrivals_by_date.get(k, Decimal("0")) + v
            for pid in entry.source_po_ids:
                if pid not in agg.source_po_ids:
                    agg.source_po_ids.append(pid)
        return agg
    m = await get_confirmed_inbound_map(db, business_id=business_id, as_of=as_of, ghost_days=ghost_days)
    return m.setdefault(str(item_id), ConfirmedInbound(item_id=str(item_id)))


@dataclass
class InboundTiming:
    """Time-aware classification of confirmed inbound for one item.

    ``usable_qty`` = inbound that arrives strictly BEFORE ``stockout_date``
    (i.e. it can genuinely cover the projected stockout, so a reorder may be
    unnecessary). ``late_qty`` = inbound at/after the stockout date or with an
    unknown arrival — it must NOT suppress an immediate reorder.
    """

    item_id: str | None
    stockout_date: date | None
    usable_qty: Decimal = Decimal("0")
    late_qty: Decimal = Decimal("0")
    total_qty: Decimal = Decimal("0")
    late_line_items: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "stockout_date": self.stockout_date.isoformat() if self.stockout_date else None,
            "usable_qty": float(self.usable_qty),
            "late_qty": float(self.late_qty),
            "total_qty": float(self.total_qty),
            "late_line_items": self.late_line_items,
        }


def usable_confirmed_inbound(
    inbound: ConfirmedInbound | None,
    *,
    stockout_date: date | None,
) -> InboundTiming:
    """Split an item's confirmed inbound into *usable-before-stockout* vs *late*.

    The stockout date is the date the on-hand stock is projected to run out
    given current velocity. Semantics:

    * Inbound whose recorded ``expected_delivery`` is STRICTLY BEFORE the
      stockout date is USABLE — it genuinely prevents the stockout.
    * Inbound whose ``expected_delivery`` is AT/AFTER the stockout date is LATE
      — it must not suppress an immediate reorder.
    * Inbound with NO recorded arrival date is treated as USABLE: it is a firm
      commitment and, per A2, committed stock counts toward coverage unless its
      timing proves it late (the conservative anti-over-order stance).

    ``stockout_date`` of ``None`` (no projected stockout) keeps everything
    usable.
    """
    total = inbound.confirmed_inbound_qty if inbound else Decimal("0")
    usable = Decimal("0")
    late = Decimal("0")
    late_lines: list[dict] = []
    if inbound is None or total <= 0:
        return InboundTiming(inbound.item_id if inbound else None, stockout_date, Decimal("0"), Decimal("0"), Decimal("0"), [])

    for line in inbound.line_items:
        arrival_s = line.get("expected_delivery")
        qty = Decimal(str(line.get("committed_qty") or "0"))
        if arrival_s is None:
            # Firm commitment with no recorded ETA -> usable (A2).
            usable += qty
            continue
        try:
            arrival = date.fromisoformat(arrival_s)
        except ValueError:
            usable += qty
            continue
        if stockout_date is None or arrival < stockout_date:
            usable += qty
        else:
            late += qty
            late_lines.append({**line, "timing": "late_at_or_after_stockout"})

    return InboundTiming(
        item_id=inbound.item_id,
        stockout_date=stockout_date,
        usable_qty=usable,
        late_qty=late,
        total_qty=total,
        late_line_items=late_lines,
    )


def projected_stockout_date(
    *,
    as_of: date,
    current_stock,
    daily_demand,
) -> date | None:
    """Date on-hand stock is projected to run out given current demand.

    Returns ``None`` when stock is already at/under zero or demand is zero
    (no meaningful stockout horizon). Inputs are coerced to ``Decimal`` so both
    ``Decimal`` and ``float`` callers are safe (e.g. the deterministic
    money-audit service and the execution guard).
    """
    try:
        current_stock = Decimal(str(current_stock))
        daily_demand = Decimal(str(daily_demand))
    except (TypeError, ValueError, InvalidOperation):
        return None
    if daily_demand <= 0 or current_stock <= 0:
        return None
    days_left = (current_stock / daily_demand).to_integral_value(rounding=ROUND_HALF_UP)
    days_left = max(days_left, 1)
    return as_of + timedelta(days=int(days_left))
