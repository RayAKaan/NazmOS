"""Time normalization (spec §16).

The audit found three date parsers giving **opposite** answers for the same input:

* ``data_normalizer.parse_date``     → ``03/04/2026`` = 3 April  (dayfirst)
* ``business_snapshot_builder``      → ``03/04/2026`` = 4 March (monthfirst)
* ``guest_audit_service``            → ``03/04/2026`` = 4 March (monthfirst)

So the same file produced different business dates depending on which entry point
received it. This module is the replacement for all three.

The governing decision: **an ambiguous numeric date is reported as ambiguous, not
guessed.** ``03/04/2026`` is either 3 April or 4 March and the string alone cannot
say which. The repository resolves this by declaring a business-wide day-first
convention, but the value carries its interpretation and its confidence so the
convention is visible rather than buried.

Malformed values never silently become the epoch or today.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone, tzinfo
from decimal import Decimal
from enum import Enum
from typing import Any, Optional, Sequence

from app.services.orbit.contracts import (
    DomainCapability,
    ErrorCategory,
    IngestionError,
    normalize_text,
)

#: Business-wide convention for slash-delimited numeric dates.
#: Day-first matches ``data_normalizer`` and Saudi/European merchant exports.
DEFAULT_DAY_FIRST = True

DEFAULT_TIMEZONE = "Asia/Riyadh"

#: Excel's epoch, including its well-known 1900 leap-year bug offset.
_EXCEL_EPOCH = date(1899, 12, 30)
_EXCEL_SERIAL_MIN = 20_000      # ~1954-10-03; below this a number is not a date
_EXCEL_SERIAL_MAX = 80_000      # ~2118; above this a number is not a date

_ISO_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ](\d{1,2}):(\d{2})(?::(\d{2}))?)?")
_NUMERIC_DATE_RE = re.compile(r"^(\d{1,4})[/\-.](\d{1,2})[/\-.](\d{1,4})$")
# Separators accepted between a day and a written month: space, dash, slash, dot.
_SEP = r"[\s\-./]+"
_MONTH_WORD = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"

# `04-Mar-2026`, `04 Mar, 2026` and `04/Mar/2026` all have to parse, so the
# separator is accepted around the month name as well as between day and month.
_DMY_TEXT_RE = re.compile(
    rf"^(\d{{1,2}})\s*(?:st|nd|rd|th)?\s*{_SEP}\s*{_MONTH_WORD}"
    rf"(?:,?\s*{_SEP}\s*|\s+)(\d{{4}})$",
    re.IGNORECASE,
)
_MDY_TEXT_RE = re.compile(
    rf"^{_MONTH_WORD},?\s*{_SEP}\s*(\d{{1,2}})(?:st|nd|rd|th)?"
    rf"(?:,?\s*{_SEP}\s*|\s+)(\d{{4}})$",
    re.IGNORECASE,
)
_EXCEL_RE = re.compile(r"^(\d{4,6})(?:\.0+)?$")

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

_MONTH_NAMES_AR = {
    "يناير": 1, "فبراير": 2, "مارس": 3, "ابريل": 4, "أبريل": 4, "مايو": 5,
    "يونيو": 6, "يوليو": 7, "اغسطس": 8, "أغسطس": 8, "سبتمبر": 9,
    "اكتوبر": 10, "أكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
}

_CURRENCY_NOISE = re.compile(r"(?i)\b(sar|usd|aed|eur|gbp)\b|ر\.?\s*س|ريال|[$€£]")

ARABIC_DIGITS = {
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
    "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
}


class DateInterpretation(str, Enum):
    """How a raw string was understood. Always recorded, never assumed."""

    ISO = "iso"
    EXCEL_SERIAL = "excel_serial"
    DAY_FIRST = "day_first"
    MONTH_FIRST = "month_first"
    TEXT_DAY_FIRST = "text_day_first"
    TEXT_MONTH_FIRST = "text_month_first"
    DATETIME = "datetime"
    UNPARSEABLE = "unparseable"


class TimeConfidence(str, Enum):
    EXACT = "exact"            # unambiguous regardless of convention
    CONVENTION_APPLIED = "convention_applied"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class NormalizedTime:
    """One time value, with everything needed to explain how it was read."""

    raw_value: Optional[str] = None
    value: Optional[datetime] = None
    business_date: Optional[date] = None
    source_timezone: Optional[str] = None
    normalized_timezone: Optional[str] = None
    interpretation: DateInterpretation = DateInterpretation.UNPARSEABLE
    confidence: TimeConfidence = TimeConfidence.UNKNOWN
    #: Populated when a numeric date admitted more than one reading.
    ambiguity: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    is_ambiguous: bool = False

    @property
    def is_known(self) -> bool:
        return self.value is not None

    @property
    def precision(self) -> str:
        if self.value is None:
            return "unknown"
        if self.value.hour or self.value.minute or self.value.second:
            return "datetime"
        return "date"

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_value": self.raw_value,
            "value": self.value.isoformat() if self.value else None,
            "business_date": self.business_date.isoformat() if self.business_date else None,
            "source_timezone": self.source_timezone,
            "normalized_timezone": self.normalized_timezone,
            "interpretation": self.interpretation.value,
            "confidence": self.confidence.value,
            "ambiguity": list(self.ambiguity),
            "is_ambiguous": self.is_ambiguous,
            "precision": self.precision,
            "notes": list(self.notes),
        }


def _ascii_digits(value: str) -> str:
    return "".join(ARABIC_DIGITS.get(ch, ch) for ch in value)


def _clean(raw: Any) -> str:
    if raw is None:
        return ""
    text = str(raw).strip()
    if not text:
        return ""
    text = _CURRENCY_NOISE.sub(" ", text)
    text = _ascii_digits(text)
    return text.strip().strip('"').strip()


def _valid(y: int, m: int, d: int) -> bool:
    try:
        date(y, m, d)
    except ValueError:
        return False
    return True


def _two_digit_year(v: int) -> int:
    """POSIX-style pivot: 69-99 → 1900s, 00-68 → 2000s."""
    return 1900 + v if v >= 69 else 2000 + v


def _business_tz(tz_name: Optional[str]) -> Optional[tzinfo]:
    if not tz_name:
        return None
    if tz_name.upper() == "UTC":
        return timezone.utc
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(tz_name)
    except Exception:
        return None


def normalize_timestamp(
    value: datetime | None,
    *,
    source_timezone: Optional[str] = None,
    normalize_timezone: Optional[str] = DEFAULT_TIMEZONE,
) -> NormalizedTime:
    """Attach timezone information to an existing datetime.

    A naive datetime is *assumed* to be in ``source_timezone`` — which is recorded
    as a note, because silently assuming UTC shifts every business date.
    """
    if value is None:
        return NormalizedTime(
            raw_value=None, interpretation=DateInterpretation.UNPARSEABLE,
            confidence=TimeConfidence.UNKNOWN, ambiguity=("no value supplied",),
        )

    notes: list[str] = []
    if value.tzinfo is None:
        notes.append(
            f"datetime carried no timezone; assumed {source_timezone or DEFAULT_TIMEZONE}"
        )
        tz = _business_tz(source_timezone) or _business_tz(DEFAULT_TIMEZONE)
        if tz is not None:
            value = value.replace(tzinfo=tz)
    else:
        notes.append("datetime already timezone-aware")

    business_date = value.date()
    return NormalizedTime(
        raw_value=value.isoformat(),
        value=value,
        business_date=business_date,
        source_timezone=source_timezone or DEFAULT_TIMEZONE,
        normalized_timezone=normalize_timezone or DEFAULT_TIMEZONE,
        interpretation=DateInterpretation.DATETIME,
        confidence=TimeConfidence.CONVENTION_APPLIED if notes and "assumed" in notes[0]
        else TimeConfidence.EXACT,
        notes=tuple(notes),
    )


def normalize_time(
    raw: Any,
    *,
    source_timezone: Optional[str] = None,
    normalize_timezone: Optional[str] = DEFAULT_TIMEZONE,
    day_first: bool = DEFAULT_DAY_FIRST,
) -> NormalizedTime:
    """Normalize one time value, preserving how it was interpreted.

    Returns ``confidence=UNKNOWN`` with the raw string retained for unparseable
    input. It never returns a fabricated date.
    """
    text = _clean(raw)
    if not text:
        return NormalizedTime(
            raw_value=None if raw is None else str(raw),
            interpretation=DateInterpretation.UNPARSEABLE,
            confidence=TimeConfidence.UNKNOWN,
            ambiguity=("empty value",),
        )

    # ISO first: 2026-03-04, 2026-03-04T10:30:00
    iso = _ISO_RE.match(text)
    if iso:
        y, mo, d = int(iso.group(1)), int(iso.group(2)), int(iso.group(3))
        if not _valid(y, mo, d):
            return _unparseable(text, f"invalid calendar date {y}-{mo:02d}-{d:02d}")
        hh = int(iso.group(4) or 0)
        mm = int(iso.group(5) or 0)
        ss = int(iso.group(6) or 0)
        tz_name = source_timezone or DEFAULT_TIMEZONE
        tz = _business_tz(tz_name) or timezone.utc
        return NormalizedTime(
            raw_value=str(raw),
            value=datetime(y, mo, d, hh, mm, ss, tzinfo=tz),
            business_date=date(y, mo, d),
            source_timezone=tz_name,
            normalized_timezone=normalize_timezone or DEFAULT_TIMEZONE,
            interpretation=DateInterpretation.ISO,
            confidence=TimeConfidence.EXACT,
        )

    # Excel serial
    serial = _EXCEL_RE.match(text)
    if serial:
        value_num = int(serial.group(1))
        if _EXCEL_SERIAL_MIN <= value_num <= _EXCEL_SERIAL_MAX:
            parsed = _EXCEL_EPOCH + timedelta(days=value_num)
            tz_name = source_timezone or DEFAULT_TIMEZONE
            tz = _business_tz(tz_name) or timezone.utc
            return NormalizedTime(
                raw_value=str(raw),
                value=datetime(parsed.year, parsed.month, parsed.day, tzinfo=tz),
                business_date=parsed,
                source_timezone=tz_name,
                normalized_timezone=normalize_timezone or DEFAULT_TIMEZONE,
                interpretation=DateInterpretation.EXCEL_SERIAL,
                confidence=TimeConfidence.EXACT,
                notes=(f"excel serial {value_num} -> {parsed.isoformat()}",),
            )
        return _unparseable(
            text, f"numeric value {value_num} is outside the plausible Excel date range"
        )

    # 04 Mar 2026
    dmy_text = _DMY_TEXT_RE.match(text)
    if dmy_text:
        d = int(dmy_text.group(1))
        mo = _MONTHS.get(dmy_text.group(2)[:3].lower(), 0)
        y = int(dmy_text.group(3))
        return _finish(text, y, mo, d, DateInterpretation.TEXT_DAY_FIRST,
                       TimeConfidence.EXACT, source_timezone, normalize_timezone)

    # Mar 04 2026
    mdy_text = _MDY_TEXT_RE.match(text)
    if mdy_text:
        mo = _MONTHS.get(mdy_text.group(1)[:3].lower(), 0)
        d = int(mdy_text.group(2))
        y = int(mdy_text.group(3))
        return _finish(text, y, mo, d, DateInterpretation.TEXT_MONTH_FIRST,
                       TimeConfidence.EXACT, source_timezone, normalize_timezone)

    # Arabic month names
    normalized = normalize_text(text)
    for ar_month, num in _MONTH_NAMES_AR.items():
        if ar_month in normalized:
            found = re.search(r"(\d{1,2})\D+(\d{4})", text)
            if found:
                return _finish(
                    text, int(found.group(2)), num, int(found.group(1)),
                    DateInterpretation.TEXT_DAY_FIRST, TimeConfidence.EXACT,
                    source_timezone, normalize_timezone,
                    notes=(f"arabic month name {ar_month!r}",),
                )

    # 03/04/2026 — the ambiguous case
    numeric = _NUMERIC_DATE_RE.match(text)
    if numeric:
        return _resolve_numeric(
            int(numeric.group(1)), int(numeric.group(2)), int(numeric.group(3)),
            raw=text, day_first=day_first, source_timezone=source_timezone,
            normalize_timezone=normalize_timezone,
        )

    return _unparseable(text, "no recognised date format")


def _finish(
    raw: str, y: int, mo: int, d: int,
    interpretation: DateInterpretation, confidence: TimeConfidence,
    source_timezone: Optional[str], normalize_timezone: Optional[str],
    notes: tuple[str, ...] = (),
) -> NormalizedTime:
    if mo == 0 or not _valid(y, mo, d):
        return _unparseable(raw, f"invalid calendar date {y}-{mo}-{d}")
    tz_name = source_timezone or DEFAULT_TIMEZONE
    tz = _business_tz(tz_name) or timezone.utc
    return NormalizedTime(
        raw_value=raw,
        value=datetime(y, mo, d, tzinfo=tz),
        business_date=date(y, mo, d),
        source_timezone=tz_name,
        normalized_timezone=normalize_timezone or DEFAULT_TIMEZONE,
        interpretation=interpretation,
        confidence=confidence,
        notes=notes,
    )


def _resolve_numeric(
    a: int, b: int, c: int, *,
    raw: str, day_first: bool,
    source_timezone: Optional[str], normalize_timezone: Optional[str],
) -> NormalizedTime:
    """Resolve ``a/b/c`` where the year position is itself not always last.

    The interesting case is ``03/04/2026``: both readings are valid dates and the
    string cannot say which is intended. The business convention decides, and the
    fact that a convention was needed is recorded.
    """
    # Unambiguous when one component exceeds 12 and therefore must be the day.
    if a > 12 and b <= 12:
        return _finish(raw, c, b, a, DateInterpretation.DAY_FIRST,
                       TimeConfidence.EXACT, source_timezone, normalize_timezone)
    if b > 12 and a <= 12:
        return _finish(raw, c, a, b, DateInterpretation.MONTH_FIRST,
                       TimeConfidence.EXACT, source_timezone, normalize_timezone)

    year = c if c > 31 else _two_digit_year(c)
    day_first_choice = _finish(raw, year, b, a, DateInterpretation.DAY_FIRST,
                              TimeConfidence.CONVENTION_APPLIED,
                              source_timezone, normalize_timezone)
    month_first_choice = _finish(raw, year, a, b, DateInterpretation.MONTH_FIRST,
                                 TimeConfidence.CONVENTION_APPLIED,
                                 source_timezone, normalize_timezone)

    if day_first_choice.value is None:
        return month_first_choice
    if month_first_choice.value is None:
        return day_first_choice

    chosen = day_first_choice if day_first else month_first_choice
    other = month_first_choice if day_first else day_first_choice
    return NormalizedTime(
        raw_value=raw,
        value=chosen.value,
        business_date=chosen.business_date,
        source_timezone=chosen.source_timezone,
        normalized_timezone=chosen.normalized_timezone,
        interpretation=chosen.interpretation,
        confidence=TimeConfidence.AMBIGUOUS,
        ambiguity=(
            f"both {chosen.business_date.isoformat()} (day-first) and "
            f"{other.business_date.isoformat()} (month-first) are valid readings; "
            f"applied the business convention {'day-first' if day_first else 'month-first'}",
        ),
        is_ambiguous=True,
        notes=(f"numeric date {raw!r} is ambiguous",),
    )


def _unparseable(raw: str, reason: str) -> NormalizedTime:
    return NormalizedTime(
        raw_value=raw,
        interpretation=DateInterpretation.UNPARSEABLE,
        confidence=TimeConfidence.UNKNOWN,
        ambiguity=(reason,),
        notes=("value retained verbatim; no date was inferred",),
    )


# ── fiscal periods ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FiscalPeriod:
    """A resolved reporting period."""

    period_start: date
    period_end: date
    label: str
    granularity: str = "month"
    fiscal_year: Optional[int] = None
    fiscal_quarter: Optional[int] = None

    @property
    def days(self) -> int:
        return (self.period_end - self.period_start).days + 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "label": self.label,
            "granularity": self.granularity,
            "fiscal_year": self.fiscal_year,
            "fiscal_quarter": self.fiscal_quarter,
            "days": self.days,
        }


def iso_week(value: date) -> tuple[int, int]:
    """ISO year and week number."""
    iso = value.isocalendar()
    return iso[0], iso[1]


def calendar_month(value: date) -> FiscalPeriod:
    start = value.replace(day=1)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return FiscalPeriod(
        period_start=start,
        period_end=end - timedelta(days=1),
        label=start.strftime("%Y-%m"),
        granularity="month",
        fiscal_year=start.year,
        fiscal_quarter=(start.month - 1) // 3 + 1,
    )


def calendar_quarter(value: date) -> FiscalPeriod:
    quarter = (value.month - 1) // 3 + 1
    start_month = 3 * (quarter - 1) + 1
    start = date(value.year, start_month, 1)
    end_month = start_month + 3
    end = date(value.year + 1, 1, 1) if end_month > 12 else date(value.year, end_month, 1)
    return FiscalPeriod(
        period_start=start,
        period_end=end - timedelta(days=1),
        label=f"{value.year}-Q{quarter}",
        granularity="quarter",
        fiscal_year=value.year,
        fiscal_quarter=quarter,
    )


def resolve_period(
    start: date, end: date, *, granularity: str = "month"
) -> Optional[FiscalPeriod]:
    """The period covering a date range, at the requested granularity."""
    if end < start:
        return None
    if granularity == "week":
        return FiscalPeriod(
            period_start=start - timedelta(days=start.weekday()),
            period_end=start - timedelta(days=start.weekday()) + timedelta(days=6),
            label=f"{start.isocalendar()[0]}-W{start.isocalendar()[1]:02d}",
            granularity="week",
        )
    if granularity == "quarter":
        return calendar_quarter(start)
    return calendar_month(start)


def date_range_days(start: date, end: date) -> int:
    """Inclusive day count. Never negative for a reversed range."""
    if end < start:
        return 0
    return (end - start).days + 1