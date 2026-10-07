"""Currency normalization (spec §18).

Non-negotiable behaviours:

* **Currency is never stripped.** A bare number stays associated with the currency
  it arrived in.
* **SAR is never assumed.** A business that trades in USD does not get SAR.
* **USD is never silently converted to SAR.** Without a rate, the normalized
  amount is ``UNKNOWN`` while the source amount and source currency are kept.
* Without an FX rate, conversion does not happen at all. Not an approximate rate,
  not a stale rate silently reused — no rate means no conversion.

The audit found currency being stripped in two places (``file_ingestion.py:234``,
``column_profiling.py:101``), which meant USD values were labelled SAR and then
summed alongside genuine SAR values.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Mapping, Optional

from app.services.orbit.contracts import ErrorCategory, IngestionError, normalize_text

#: ISO 4217 code -> display metadata.
CURRENCIES: dict[str, dict[str, Any]] = {
    "SAR": {"name": "Saudi Riyal", "symbol": "ر.س", "minor_unit": 2},
    "USD": {"name": "US Dollar", "symbol": "$", "minor_unit": 2},
    "EUR": {"name": "Euro", "symbol": "€", "minor_unit": 2},
    "GBP": {"name": "Pound Sterling", "symbol": "£", "minor_unit": 2},
    "AED": {"name": "UAE Dirham", "symbol": "د.إ", "minor_unit": 2},
    "KWD": {"name": "Kuwaiti Dinar", "symbol": "د.ك", "minor_unit": 3},
    "QAR": {"name": "Qatari Riyal", "symbol": "ر.ق", "minor_unit": 2},
    "BHD": {"name": "Bahraini Dinar", "symbol": "د.ب", "minor_unit": 3},
    "OMR": {"name": "Omani Rial", "symbol": "ر.ع", "minor_unit": 3},
    "EGP": {"name": "Egyptian Pound", "symbol": "ج.م", "minor_unit": 2},
    "JOD": {"name": "Jordanian Dinar", "symbol": "د.أ", "minor_unit": 3},
    "PKR": {"name": "Pakistani Rupee", "symbol": "₨", "minor_unit": 2},
    "INR": {"name": "Indian Rupee", "symbol": "₹", "minor_unit": 2},
    "TRY": {"name": "Turkish Lira", "symbol": "₺", "minor_unit": 2},
}

#: Text and symbol forms mapped to ISO codes. Longest forms first so that
#: "usd" is not matched by a shorter overlapping token.
_CURRENCY_PATTERNS: tuple[tuple[str, str], ...] = (
    ("ريال سعودي", "SAR"), ("ريال", "SAR"), ("ر.س", "SAR"), ("ر س", "SAR"),
    ("saudi", "SAR"), ("sr", "SAR"), ("sar", "SAR"),
    ("usd", "USD"), ("us dollar", "USD"), ("dollar", "USD"), ("$", "USD"),
    ("eur", "EUR"), ("euro", "EUR"), ("€", "EUR"),
    ("gbp", "GBP"), ("pound", "GBP"), ("£", "GBP"),
    ("aed", "AED"), ("dirham", "AED"), ("د.إ", "AED"),
    ("kwd", "KWD"), ("د.ك", "KWD"),
    ("qar", "QAR"), ("ريال قطري", "QAR"),
    ("bhd", "BHD"), ("د.ب", "BHD"),
    ("omr", "OMR"), ("ريال عماني", "OMR"),
    ("egp", "EGP"), ("ج.م", "EGP"),
    ("jod", "JOD"), ("د.أ", "JOD"),
    ("pkr", "PKR"), ("inr", "INR"), ("₹", "INR"),
    ("try", "TRY"), ("₺", "TRY"),
)

_AMOUNT_RE = re.compile(
    r"(?P<sign>-)?\s*(?P<sym>[$€£₹₨﷼]|ر\.?\s*س|د\.?\s*[إكبعأ]\.?)?\s*"
    r"(?P<num>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<suffix>ريال|ريال سعودي|درهم|دينار|ريال قطري|ريال عماني)?",
)

ARABIC_DIGITS = {
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
    "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
}


class ConversionMethod(str, Enum):
    NONE = "none"
    DIRECT_RATE = "direct_rate"
    INVERSE_RATE = "inverse_rate"
    CROSS_RATE = "cross_rate"


@dataclass(frozen=True)
class ExchangeRate:
    """One auditable rate, with everything needed to reproduce the conversion."""

    base: str
    quote: str
    rate: Decimal
    rate_timestamp: datetime
    rate_source: str
    method: ConversionMethod = ConversionMethod.DIRECT_RATE

    def to_dict(self) -> dict[str, Any]:
        return {
            "base": self.base,
            "quote": self.quote,
            "rate": str(self.rate),
            "rate_timestamp": self.rate_timestamp.isoformat(),
            "rate_source": self.rate_source,
            "method": self.method.value,
        }


@dataclass(frozen=True)
class NormalizedMoney:
    """A monetary amount that always remembers what it was."""

    raw_amount: Optional[str] = None
    source_amount: Optional[Decimal] = None
    source_currency: Optional[str] = None

    normalized_amount: Optional[Decimal] = None
    normalized_currency: Optional[str] = None

    exchange_rate: Optional[Decimal] = None
    rate_timestamp: Optional[datetime] = None
    rate_source: Optional[str] = None
    conversion_method: ConversionMethod = ConversionMethod.NONE

    #: True when an amount exists but its currency could not be established.
    currency_ambiguous: bool = False
    notes: tuple[str, ...] = ()

    @property
    def is_converted(self) -> bool:
        return (
            self.normalized_amount is not None
            and self.normalized_currency is not None
            and self.conversion_method is not ConversionMethod.NONE
        )

    @property
    def is_known(self) -> bool:
        """Whether we know the monetary value in a stated currency."""
        return self.normalized_amount is not None and self.normalized_currency is not None

    @property
    def status(self) -> str:
        if self.is_converted:
            return "converted"
        if self.source_amount is not None and self.source_currency:
            return "source_only"
        if self.source_amount is not None:
            return "currency_unknown"
        return "unknown"

    @property
    def display_value(self) -> Optional[Decimal]:
        """The amount to report, in whichever currency it is actually known in.

        Prefers the converted value, but falls back to the source amount *with
        its own currency*. This is what keeps a USD figure from being displayed
        beside SAR figures as though they were comparable.
        """
        if self.normalized_amount is not None:
            return self.normalized_amount
        return self.source_amount

    @property
    def display_currency(self) -> Optional[str]:
        """Currency that pairs with :attr:`display_value`. Never a guess."""
        if self.normalized_amount is not None:
            return self.normalized_currency
        return self.source_currency

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_amount": self.raw_amount,
            "source_amount": str(self.source_amount) if self.source_amount is not None else None,
            "source_currency": self.source_currency,
            "normalized_amount": (
                str(self.normalized_amount) if self.normalized_amount is not None else None
            ),
            "normalized_currency": self.normalized_currency,
            "exchange_rate": str(self.exchange_rate) if self.exchange_rate is not None else None,
            "rate_timestamp": self.rate_timestamp.isoformat() if self.rate_timestamp else None,
            "rate_source": self.rate_source,
            "conversion_method": self.conversion_method.value,
            "currency_ambiguous": self.currency_ambiguous,
            "status": self.status,
            "is_known": self.is_known,
            "notes": list(self.notes),
        }


def detect_currency(text: Any) -> Optional[str]:
    """Detect an ISO currency code from free text. Returns ``None``, never a guess."""
    if text is None:
        return None
    raw = str(text)
    lowered = "".join(ARABIC_DIGITS.get(ch, ch) for ch in raw).lower()
    for pattern, code in _CURRENCY_PATTERNS:
        if pattern in lowered:
            return code
    return None


def extract_amount(text: Any) -> Optional[Decimal]:
    """Extract a numeric amount from text, or ``None`` if there isn't one.

    ``None`` rather than ``0`` is essential: a malformed amount must never become
    a zero contribution to a total.
    """
    if text is None:
        return None
    if isinstance(text, Decimal):
        return text
    raw = str(text).strip()
    if not raw:
        return None
    ascii_text = "".join(ARABIC_DIGITS.get(ch, ch) for ch in raw)
    # Parenthesised negatives are the accounting convention for credits.
    negative = ascii_text.startswith("(") and ascii_text.endswith(")")
    match = _AMOUNT_RE.search(ascii_text)
    if not match:
        return None
    try:
        amount = Decimal(match.group("num").replace(",", ""))
    except Exception:
        return None
    if negative:
        amount = -amount
    if match.group("sign"):
        amount = -abs(amount)
    return amount


def normalize_money(
    raw_amount: Any,
    *,
    raw_text: Any = None,
    source_currency: Optional[str] = None,
    target_currency: Optional[str] = None,
    rates: Optional[Mapping[str, ExchangeRate]] = None,
    allow_inferred_currency: bool = False,
) -> NormalizedMoney:
    """Normalize one monetary value, converting only when a rate genuinely exists.

    The source currency is detected from the text when not supplied. If it still
    cannot be established, the amount is kept with ``currency_ambiguous`` set and
    no conversion is attempted — a number without a currency cannot be summed
    against numbers in other currencies.
    """
    text = raw_text if raw_text is not None else raw_amount
    amount = extract_amount(raw_amount if raw_amount is not None else text)
    raw_str = None if raw_amount is None else str(raw_amount)

    notes: list[str] = []
    currency = (source_currency or "").strip().upper() or None

    if currency and currency not in CURRENCIES:
        # An unrecognised currency code is rejected outright rather than
        # silently dropped, which would leave the amount looking unit-less.
        raise IngestionError(
            ErrorCategory.CURRENCY_ERROR,
            f"currency {currency!r} is not a recognised ISO 4217 code",
            locator=currency,
        )

    if currency is None:
        currency = detect_currency(text)
        if currency:
            notes.append(f"currency {currency!r} detected from the source text")
        elif allow_inferred_currency and amount is not None:
            currency = None
            notes.append(
                "no currency marker present; left unknown rather than assuming SAR"
            )

    if amount is None:
        # Deliberately returns no ``source_amount``: a value we could not parse is
        # unknown, and representing it as ``0`` would silently change a total.
        return NormalizedMoney(
            raw_amount=raw_str, source_currency=currency,
            notes=tuple(notes + ["no amount could be parsed; not treated as zero"]),
        )

    # A value whose currency is still unknown must not be normalized at all,
    # not even against itself: a currency-less number is not a monetary amount.
    if not target_currency:
        if currency is None:
            return NormalizedMoney(
                raw_amount=raw_str,
                source_amount=amount,
                source_currency=None,
                currency_ambiguous=True,
                notes=tuple(
                    notes
                    + ["amount present but currency unknown; not converted and not summed"]
                ),
            )
        target_currency = currency
    else:
        target_currency = target_currency.strip().upper()
        if target_currency not in CURRENCIES:
            raise IngestionError(
                ErrorCategory.CURRENCY_ERROR,
                f"target currency {target_currency!r} is not a recognised ISO 4217 code",
                locator=target_currency,
            )

    if currency is None:
        return NormalizedMoney(
            raw_amount=raw_str,
            source_amount=amount,
            source_currency=None,
            currency_ambiguous=True,
            notes=tuple(
                notes
                + ["amount present but currency unknown; not converted and not summed"]
            ),
        )

    if target_currency == currency:
        return NormalizedMoney(
            raw_amount=raw_str,
            source_amount=amount,
            source_currency=currency,
            normalized_amount=amount,
            normalized_currency=currency,
            notes=tuple(notes),
        )

    rate = (rates or {}).get(f"{currency}->{target_currency}")
    if rate is None:
        # No rate means no conversion. This is the whole point of the module.
        return NormalizedMoney(
            raw_amount=raw_str,
            source_amount=amount,
            source_currency=currency,
            normalized_amount=None,
            normalized_currency=None,
            notes=tuple(
                notes
                + [
                    f"no exchange rate available for {currency}->{target_currency}; "
                    "source amount and currency preserved, normalized amount left unknown"
                ]
            ),
        )

    return NormalizedMoney(
        raw_amount=raw_str,
        source_amount=amount,
        source_currency=currency,
        normalized_amount=amount * rate.rate,
        normalized_currency=target_currency,
        exchange_rate=rate.rate,
        rate_timestamp=rate.rate_timestamp,
        rate_source=rate.rate_source,
        conversion_method=rate.method,
        notes=tuple(notes),
    )


def sum_money(values: Iterable[NormalizedMoney]) -> Optional[Decimal]:
    """Sum amounts **only** when they share one currency.

    Mixing currencies without a rate produces a meaningless number, so the sum is
    refused rather than approximated. An empty or unknown-currency set sums to
    ``None`` (unknown), never ``0``.
    """
    known: list[tuple[str, Decimal]] = []
    for money in values:
        if money.normalized_amount is not None and money.normalized_currency:
            known.append((money.normalized_currency, money.normalized_amount))

    if not known:
        return None

    currencies = {c for c, _ in known}
    if len(currencies) > 1:
        raise IngestionError(
            ErrorCategory.CURRENCY_ERROR,
            f"refusing to sum mixed currencies: {sorted(currencies)}",
            detail={"currencies": sorted(currencies)},
        )
    total = sum((amount for _, amount in known), Decimal(0))
    return total.quantize(Decimal("0.01"))


def distinct_currencies(values: Iterable[NormalizedMoney]) -> tuple[str, ...]:
    """Every currency present, so a multi-currency business is visible."""
    return tuple(sorted({m.normalized_currency for m in values if m.normalized_currency}))


def supported_currencies() -> tuple[str, ...]:
    return tuple(sorted(CURRENCIES))