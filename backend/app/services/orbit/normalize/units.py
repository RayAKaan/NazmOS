"""Unit normalization (spec §17).

A dimensional model, so conversions are only possible *within* a dimension:

    mass    kg ↔ g ↔ t
    volume  L ↔ ml
    count   unit ↔ dozen ↔ gross
    length  m ↔ cm ↔ mm
    time    hour ↔ minute ↔ day

**Incompatible dimensions never convert.** ``kg → liters`` fails, because doing
so silently would produce a number that looks authoritative and means nothing.

Conversions that need business context rather than arithmetic (density, pack size)
are *not* attempted here: they require domain-specific metadata, and inventing one
is worse than declining. The raw unit is always preserved regardless of outcome.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from app.services.orbit.contracts import ErrorCategory, IngestionError, normalize_text


class Dimension(str, Enum):
    MASS = "mass"
    VOLUME = "volume"
    COUNT = "count"
    LENGTH = "length"
    TIME = "time"
    CURRENCY = "currency"
    NONE = "none"          # unknown / unspecified


#: Canonical unit -> (dimension, factor to the dimension's base unit).
#: Base units: kg, L, unit, m, hour.
UNIT_TABLE: dict[str, tuple[Dimension, Decimal]] = {
    # mass
    "kg": (Dimension.MASS, Decimal(1)),
    "kgs": (Dimension.MASS, Decimal(1)),
    "kilogram": (Dimension.MASS, Decimal(1)),
    "kilograms": (Dimension.MASS, Decimal(1)),
    "كجم": (Dimension.MASS, Decimal(1)),
    "g": (Dimension.MASS, Decimal("0.001")),
    "gm": (Dimension.MASS, Decimal("0.001")),
    "gram": (Dimension.MASS, Decimal("0.001")),
    "grams": (Dimension.MASS, Decimal("0.001")),
    "جم": (Dimension.MASS, Decimal("0.001")),
    "t": (Dimension.MASS, Decimal(1000)),
    "tonne": (Dimension.MASS, Decimal(1000)),
    "tonnes": (Dimension.MASS, Decimal(1000)),
    "ton": (Dimension.MASS, Decimal(1000)),
    "tonne_s": (Dimension.MASS, Decimal(1000)),
    "lb": (Dimension.MASS, Decimal("0.45359237")),
    "lbs": (Dimension.MASS, Decimal("0.45359237")),
    "pound": (Dimension.MASS, Decimal("0.45359237")),
    "oz": (Dimension.MASS, Decimal("0.028349523125")),

    # volume
    "l": (Dimension.VOLUME, Decimal(1)),
    "ltr": (Dimension.VOLUME, Decimal(1)),
    "liter": (Dimension.VOLUME, Decimal(1)),
    "liters": (Dimension.VOLUME, Decimal(1)),
    "litre": (Dimension.VOLUME, Decimal(1)),
    "litres": (Dimension.VOLUME, Decimal(1)),
    "لتر": (Dimension.VOLUME, Decimal(1)),
    "مل": (Dimension.VOLUME, Decimal("0.001")),
    "ml": (Dimension.VOLUME, Decimal("0.001")),
    "milliliter": (Dimension.VOLUME, Decimal("0.001")),
    "millilitre": (Dimension.VOLUME, Decimal("0.001")),
    "cl": (Dimension.VOLUME, Decimal("0.01")),
    "dl": (Dimension.VOLUME, Decimal("0.1")),
    "gal": (Dimension.VOLUME, Decimal("3.785411784")),
    "gallon": (Dimension.VOLUME, Decimal("3.785411784")),

    # count
    "unit": (Dimension.COUNT, Decimal(1)),
    "units": (Dimension.COUNT, Decimal(1)),
    "pcs": (Dimension.COUNT, Decimal(1)),
    "pc": (Dimension.COUNT, Decimal(1)),
    "piece": (Dimension.COUNT, Decimal(1)),
    "pieces": (Dimension.COUNT, Decimal(1)),
    "ea": (Dimension.COUNT, Decimal(1)),
    "each": (Dimension.COUNT, Decimal(1)),
    "item": (Dimension.COUNT, Decimal(1)),
    "items": (Dimension.COUNT, Decimal(1)),
    "قطعة": (Dimension.COUNT, Decimal(1)),
    "حبة": (Dimension.COUNT, Decimal(1)),
    "عدد": (Dimension.COUNT, Decimal(1)),
    "dozen": (Dimension.COUNT, Decimal(12)),
    "dozens": (Dimension.COUNT, Decimal(12)),
    "gross": (Dimension.COUNT, Decimal(144)),
    "doz": (Dimension.COUNT, Decimal(12)),

    # length
    "m": (Dimension.LENGTH, Decimal(1)),
    "meter": (Dimension.LENGTH, Decimal(1)),
    "meters": (Dimension.LENGTH, Decimal(1)),
    "metre": (Dimension.LENGTH, Decimal(1)),
    "متر": (Dimension.LENGTH, Decimal(1)),
    "cm": (Dimension.LENGTH, Decimal("0.01")),
    "mm": (Dimension.LENGTH, Decimal("0.001")),
    "km": (Dimension.LENGTH, Decimal(1000)),
    "inch": (Dimension.LENGTH, Decimal("0.0254")),
    "inches": (Dimension.LENGTH, Decimal("0.0254")),
    "ft": (Dimension.LENGTH, Decimal("0.3048")),
    "feet": (Dimension.LENGTH, Decimal("0.3048")),
    "yard": (Dimension.LENGTH, Decimal("0.9144")),

    # time
    "hour": (Dimension.TIME, Decimal(1)),
    "hours": (Dimension.TIME, Decimal(1)),
    "hr": (Dimension.TIME, Decimal(1)),
    "hrs": (Dimension.TIME, Decimal(1)),
    "h": (Dimension.TIME, Decimal(1)),
    "ساعة": (Dimension.TIME, Decimal(1)),
    "د": (Dimension.TIME, Decimal(1)),
    # Decimal has no fraction literal: "1/60" is a syntax error, so the
    # per-minute factor is written as a division of two decimals.
    "minute": (Dimension.TIME, Decimal(1) / Decimal(60)),
    "minutes": (Dimension.TIME, Decimal(1) / Decimal(60)),
    "min": (Dimension.TIME, Decimal(1) / Decimal(60)),
    "دقيقة": (Dimension.TIME, Decimal(1) / Decimal(60)),
    "day": (Dimension.TIME, Decimal(24)),
    "days": (Dimension.TIME, Decimal(24)),
    "يوم": (Dimension.TIME, Decimal(24)),
    "week": (Dimension.TIME, Decimal(168)),
    "weeks": (Dimension.TIME, Decimal(168)),
    "أسبوع": (Dimension.TIME, Decimal(168)),

    # currency is dimensioned so money units are never confused with mass
    "sar": (Dimension.CURRENCY, Decimal(1)),
    "usd": (Dimension.CURRENCY, Decimal(1)),
    "eur": (Dimension.CURRENCY, Decimal(1)),
    "aed": (Dimension.CURRENCY, Decimal(1)),
    "ريال": (Dimension.CURRENCY, Decimal(1)),
}

#: Tokens that indicate a unit without being a unit. Treated as unknown rather
#: than guessed, because "each" and "box" imply business-specific pack sizes.
AMBIGUOUS_UNITS = frozenset({
    "box", "boxes", "case", "cases", "pack", "packs", "packet", "carton", "bag",
    "bottle", "roll", "rolls", "set", "sets", "kit", "sack", "bin", "tray",
    "علبة", "كرتون", "كيس", "زجاجة", "عبوة", "رزمه",
})

_UNIT_INDEX: dict[str, tuple[Dimension, Decimal]] = {normalize_text(k): v for k, v in UNIT_TABLE.items()}


@dataclass(frozen=True)
class NormalizedUnit:
    """A quantity with its dimension, preserving the unit it came from."""

    raw_value: Optional[str] = None
    raw_unit: Optional[str] = None
    value: Optional[Decimal] = None
    dimension: Dimension = Dimension.NONE
    canonical_unit: Optional[str] = None
    #: Set when the unit is recognisable but its factor is not implied (e.g. box).
    is_ambiguous: bool = False
    notes: tuple[str, ...] = ()

    @property
    def is_known(self) -> bool:
        return self.value is not None and self.dimension is not Dimension.NONE

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_value": self.raw_value,
            "raw_unit": self.raw_unit,
            "value": str(self.value) if self.value is not None else None,
            "dimension": self.dimension.value,
            "canonical_unit": self.canonical_unit,
            "is_ambiguous": self.is_ambiguous,
            "is_known": self.is_known,
            "notes": list(self.notes),
        }


def dimension_of(unit: Optional[str]) -> Dimension:
    """The dimension a unit belongs to, or ``NONE`` if unrecognised."""
    if not unit:
        return Dimension.NONE
    entry = _UNIT_INDEX.get(normalize_text(unit))
    return entry[0] if entry else Dimension.NONE


def parse_unit(unit: Optional[str]) -> Optional[str]:
    """Canonical spelling of a unit, if recognised."""
    if not unit:
        return None
    normalized = normalize_text(unit)
    if normalized not in _UNIT_INDEX:
        return None
    for canonical in UNIT_TABLE:
        if normalize_text(canonical) == normalized:
            return canonical
    return unit.strip()


def is_ambiguous_unit(unit: Optional[str]) -> bool:
    if not unit:
        return False
    return normalize_text(unit) in AMBIGUOUS_UNITS


def normalize_quantity(
    value: Any,
    unit: Optional[str] = None,
    *,
    target_unit: Optional[str] = None,
    strict: bool = True,
) -> NormalizedUnit:
    """Attach a dimension to a quantity, optionally converting it.

    ``strict=True`` raises on an unknown or ambiguous unit. ``strict=False``
    returns a value with ``dimension=NONE`` instead, so a caller that prefers a
    gap to an exception can have one. Neither mode invents a unit.
    """
    raw_unit = unit.strip() if unit else None

    if is_ambiguous_unit(raw_unit):
        msg = (
            f"unit {raw_unit!r} implies a business-specific pack size; no conversion "
            "is possible without explicit conversion metadata"
        )
        if strict:
            raise IngestionError(ErrorCategory.UNIT_ERROR, msg, locator=raw_unit)
        return NormalizedUnit(
            raw_value=None if value is None else str(value),
            raw_unit=raw_unit,
            is_ambiguous=True,
            notes=(msg,),
        )

    dim = dimension_of(raw_unit)
    if dim is Dimension.NONE:
        msg = f"unit {raw_unit!r} is not a recognised unit of measure"
        if strict:
            raise IngestionError(ErrorCategory.UNIT_ERROR, msg, locator=raw_unit)
        return NormalizedUnit(
            raw_value=None if value is None else str(value),
            raw_unit=raw_unit,
            notes=(msg,),
        )

    entry = _UNIT_INDEX[normalize_text(raw_unit)]
    factor = entry[1]
    notes: list[str] = []

    numeric: Optional[Decimal]
    if value is None or str(value).strip() == "":
        numeric = None
        notes.append("no quantity supplied; dimension known but magnitude unknown")
    else:
        try:
            numeric = Decimal(str(value).strip().replace(",", ""))
        except Exception:
            msg = f"quantity {value!r} is not a number"
            if strict:
                raise IngestionError(ErrorCategory.UNIT_ERROR, msg, locator=str(value))
            return NormalizedUnit(
                raw_value=str(value), raw_unit=raw_unit, dimension=dim, notes=(msg,)
            )

    if target_unit:
        # Convert relative to the dimension base unit, so a conversion is
        # source-factor -> base -> target-factor. Multiplying by the target
        # factor instead would scale in the wrong direction (2 kg -> g would
        # yield 0.002 instead of 2000).
        target_dim = dimension_of(target_unit)
        if target_dim is Dimension.NONE:
            raise IngestionError(
                ErrorCategory.UNIT_ERROR,
                f"target unit {target_unit!r} is not a recognised unit",
                locator=target_unit,
            )
        if target_dim is not dim:
            # This is the guarantee that matters: kg to liters is refused.
            raise IngestionError(
                ErrorCategory.UNIT_ERROR,
                f"cannot convert {dim.value} to {target_dim.value}: "
                f"{raw_unit!r} -> {target_unit!r} is dimensionally incompatible",
                locator=target_unit,
            )
        if numeric is not None:
            numeric = _convert(dim, numeric * factor, target_unit)

    return NormalizedUnit(
        raw_value=None if value is None else str(value),
        raw_unit=raw_unit,
        value=numeric,
        dimension=dim,
        canonical_unit=target_unit or raw_unit,
        notes=tuple(notes),
    )


def _convert(dim: Dimension, base_value: Decimal, target_unit: str) -> Decimal:
    """Convert a base-unit magnitude into ``target_unit``."""
    target_factor = _UNIT_INDEX[normalize_text(target_unit)][1]
    if target_factor == 0:
        raise IngestionError(
            ErrorCategory.UNIT_ERROR,
            f"target unit {target_unit!r} has no conversion factor",
            locator=target_unit,
        )
    return base_value / target_factor


def convert(
    value: Decimal, from_unit: str, to_unit: str
) -> Decimal:
    """Convert within a dimension, raising on incompatibility."""
    src_dim = dimension_of(from_unit)
    dst_dim = dimension_of(to_unit)
    if src_dim is Dimension.NONE or dst_dim is Dimension.NONE:
        raise IngestionError(
            ErrorCategory.UNIT_ERROR,
            f"unknown unit in {from_unit!r} -> {to_unit!r}",
            locator=f"{from_unit}->{to_unit}",
        )
    if src_dim is not dst_dim:
        raise IngestionError(
            ErrorCategory.UNIT_ERROR,
            f"cannot convert {from_unit!r} ({src_dim.value}) to "
            f"{to_unit!r} ({dst_dim.value}): incompatible dimensions",
            locator=f"{from_unit}->{to_unit}",
        )
    return _convert(src_dim, value * _UNIT_INDEX[normalize_text(from_unit)][1], to_unit)


def compatible(left: Optional[str], right: Optional[str]) -> bool:
    """Whether two units may be compared or aggregated."""
    a, b = dimension_of(left), dimension_of(right)
    return a is not b.NONE and a is b