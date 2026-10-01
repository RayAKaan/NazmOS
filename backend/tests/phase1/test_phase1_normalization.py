"""Stage 4: time, unit and currency normalization.

Three date parsers previously gave **opposite** answers for ``03/04/2026``
(``data_normalizer`` said 3 April, ``business_snapshot_builder`` and
``guest_audit_service`` said 4 March), and currency marks were stripped in two
places so USD values were labelled SAR.

Time tests pin that ``03/04/2026`` is now unambiguous in behaviour and explicitly
marked ambiguous in content: the business convention decides, and the fact that a
convention was required is recorded on the value.

Unit tests pin that ``kg -> liters`` is refused and that pack-size words like
``box`` are declined rather than guessed.

Currency tests pin that no rate means no conversion, that mixed currencies are
never summed, and that an empty sum is ``None`` rather than ``0``.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.services.orbit.contracts import ErrorCategory, IngestionError
from app.services.orbit.normalize import (
    ConversionMethod,
    DateInterpretation,
    Dimension,
    ExchangeRate,
    TimeConfidence,
    calendar_month,
    calendar_quarter,
    compatible,
    convert,
    date_range_days,
    detect_currency,
    dimension_of,
    distinct_currencies,
    extract_amount,
    is_ambiguous_unit,
    normalize_money,
    normalize_quantity,
    normalize_time,
    normalize_timestamp,
    resolve_period,
    sum_money,
)


# ── time ────────────────────────────────────────────────────────────────────

class TestTimeNormalization:
    def test_iso_date_is_exact(self):
        result = normalize_time("2026-04-03")
        assert result.business_date == date(2026, 4, 3)
        assert result.confidence is TimeConfidence.EXACT
        assert result.is_ambiguous is False

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("25/12/2026", date(2026, 12, 25)),   # day > 12 forces day-first
            ("12/25/2026", date(2026, 12, 25)),   # second component > 12 forces month-first
            ("04 Mar 2026", date(2026, 3, 4)),
            ("Mar 04, 2026", date(2026, 3, 4)),
            ("04-Mar-2026", date(2026, 3, 4)),
            ("2026-03-04T10:30:00", date(2026, 3, 4)),
        ],
    )
    def test_unambiguous_formats(self, raw, expected):
        assert normalize_time(raw).business_date == expected

    def test_ambiguous_numeric_date_is_flagged_not_guessed(self):
        """03/04/2026 is either 3 April or 4 March and cannot say which."""
        result = normalize_time("03/04/2026")
        assert result.confidence is TimeConfidence.AMBIGUOUS
        assert result.is_ambiguous is True
        assert result.ambiguity
        # The convention decides, but both readings are stated.
        assert result.business_date == date(2026, 4, 3)
        assert "month-first" in result.ambiguity[0]

    def test_ambiguous_date_honours_month_first_convention(self):
        result = normalize_time("03/04/2026", day_first=False)
        assert result.business_date == date(2026, 3, 4)
        assert result.is_ambiguous is True

    def test_every_path_agrees_for_the_same_input(self):
        """The defect being fixed: different entry points gave different dates.

        ``03/04/2026`` under the day-first convention is 3 April, and every other
        spelling of 3 April must agree with it — including the one that used to
        resolve differently in the guest path.
        """
        representations = ["2026-04-03", "03/04/2026", "3 Apr 2026", "Apr 03, 2026"]
        dates = {normalize_time(raw).business_date for raw in representations}
        assert dates == {date(2026, 4, 3)}, (
            f"representations of 3 April 2026 disagreed: {dates}"
        )

    def test_written_month_names_ignore_the_convention(self):
        """``3 Apr 2026`` is 3 April whichever convention is configured.

        Only a purely numeric date can be ambiguous. A written month name has one
        reading, so the convention must not change it.
        """
        for day_first in (True, False):
            assert normalize_time("3 Apr 2026", day_first=day_first).business_date == date(
                2026, 4, 3
            )
            assert normalize_time("Apr 03, 2026", day_first=day_first).business_date == date(
                2026, 4, 3
            )

    def test_only_numeric_dates_are_ambiguous(self):
        ambiguous = {"03/04/2026", "04/03/2026"}
        certain = ["2026-04-03", "3 Apr 2026", "Apr 03, 2026", "25/12/2026", "45000"]
        for raw in certain:
            assert normalize_time(raw).is_ambiguous is False, raw
        for raw in ambiguous:
            assert normalize_time(raw).is_ambiguous is True, raw

    def test_excel_serial_dates(self):
        result = normalize_time("45000")
        assert result.interpretation is DateInterpretation.EXCEL_SERIAL
        assert result.business_date == date(2023, 3, 15)

    def test_out_of_range_serial_is_not_a_date(self):
        result = normalize_time("999999")
        assert result.value is None
        assert result.confidence is TimeConfidence.UNKNOWN

    def test_garbage_keeps_raw_value_and_invents_nothing(self):
        result = normalize_time("not a date")
        assert result.value is None
        assert result.business_date is None
        assert result.raw_value == "not a date"
        assert result.confidence is TimeConfidence.UNKNOWN

    def test_invalid_calendar_date_rejected(self):
        assert normalize_time("2026-02-30").value is None

    def test_empty_value_is_unknown(self):
        assert normalize_time("").value is None

    def test_raw_value_always_preserved(self):
        result = normalize_time("2026-04-03")
        assert result.raw_value == "2026-04-03"

    def test_source_timezone_is_recorded(self):
        result = normalize_time("2026-04-03", source_timezone="Asia/Riyadh")
        assert result.source_timezone == "Asia/Riyadh"
        assert result.business_date == date(2026, 4, 3)

    def test_naive_timestamp_assumption_is_disclosed(self):
        result = normalize_timestamp(datetime(2026, 4, 3, 23, 30))
        assert any("assumed" in n for n in result.notes)

    def test_aware_timestamp_is_not_reinterpreted(self):
        aware = datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc)
        result = normalize_timestamp(aware)
        assert any("already timezone-aware" in n for n in result.notes)

    def test_precision_is_reported(self):
        assert normalize_time("2026-04-03").precision == "date"
        assert normalize_time("2026-04-03T10:00:00").precision == "datetime"
        assert normalize_time("nonsense").precision == "unknown"


class TestFiscalPeriods:
    def test_calendar_month(self):
        period = calendar_month(date(2026, 3, 15))
        assert period.period_start == date(2026, 3, 1)
        assert period.period_end == date(2026, 3, 31)
        assert period.label == "2026-03"

    def test_december_month_rolls_the_year(self):
        period = calendar_month(date(2026, 12, 5))
        assert period.period_start == date(2026, 12, 1)
        assert period.period_end == date(2026, 12, 31)

    def test_calendar_quarter(self):
        period = calendar_quarter(date(2026, 5, 1))
        assert period.period_start == date(2026, 4, 1)
        assert period.period_end == date(2026, 6, 30)
        assert period.label == "2026-Q2"

    def test_week_period(self):
        period = resolve_period(date(2026, 4, 3), date(2026, 4, 9), granularity="week")
        assert period.period_start.weekday() == 0

    def test_reversed_range_returns_none(self):
        assert resolve_period(date(2026, 4, 9), date(2026, 4, 1)) is None

    def test_inclusive_day_count(self):
        assert date_range_days(date(2026, 4, 1), date(2026, 4, 30)) == 30
        assert date_range_days(date(2026, 4, 1), date(2026, 4, 1)) == 1
        assert date_range_days(date(2026, 4, 30), date(2026, 4, 1)) == 0


# ── units ───────────────────────────────────────────────────────────────────

class TestUnits:
    def test_mass_conversion(self):
        assert normalize_quantity(2, "kg", target_unit="g").value == Decimal("2000")

    def test_volume_conversion(self):
        assert normalize_quantity(2, "L", target_unit="ml").value == Decimal("2000")

    def test_count_conversion(self):
        assert normalize_quantity(12, "units", target_unit="dozen").value == Decimal(1)

    def test_time_conversion(self):
        assert normalize_quantity(2, "hour", target_unit="minute").value == Decimal(120)

    def test_incompatible_dimensions_are_refused(self):
        """kg -> liters must fail; doing it silently would invent a number."""
        with pytest.raises(IngestionError) as exc:
            normalize_quantity(2, "kg", target_unit="L")
        assert exc.value.category is ErrorCategory.UNIT_ERROR
        assert "incompatible" in str(exc.value)

    def test_mass_to_count_refused(self):
        with pytest.raises(IngestionError):
            normalize_quantity(1, "kg", target_unit="units")

    def test_ambiguous_pack_units_are_refused(self):
        """A 'box' has no arithmetic relationship to a unit without metadata."""
        with pytest.raises(IngestionError) as exc:
            normalize_quantity(5, "box")
        assert exc.value.category is ErrorCategory.UNIT_ERROR
        assert "pack size" in str(exc.value)

    def test_non_strict_mode_reports_ambiguity(self):
        result = normalize_quantity(5, "box", strict=False)
        assert result.is_ambiguous is True
        assert result.value is None

    def test_unknown_unit_is_refused(self):
        with pytest.raises(IngestionError):
            normalize_quantity(5, "flurbles")

    def test_raw_unit_always_preserved(self):
        result = normalize_quantity(2, "kg", target_unit="g")
        assert result.raw_unit == "kg"
        assert result.raw_value == "2"

    def test_missing_quantity_does_not_become_zero(self):
        result = normalize_quantity(None, "kg")
        assert result.value is None
        assert result.dimension is Dimension.MASS

    def test_malformed_quantity_does_not_become_zero(self):
        with pytest.raises(IngestionError):
            normalize_quantity("about two", "kg")

    def test_dimension_lookup(self):
        assert dimension_of("kg") is Dimension.MASS
        assert dimension_of("L") is Dimension.VOLUME
        assert dimension_of("pcs") is Dimension.COUNT
        assert dimension_of("unknown") is Dimension.NONE

    def test_compatibility_check(self):
        assert compatible("kg", "g") is True
        assert compatible("kg", "L") is False
        assert compatible(None, "L") is False

    def test_convert_function(self):
        assert convert(Decimal(2), "kg", "g") == Decimal("2000")
        with pytest.raises(IngestionError):
            convert(Decimal(2), "kg", "L")

    def test_arabic_units(self):
        assert dimension_of("كجم") is Dimension.MASS
        assert dimension_of("قطعة") is Dimension.COUNT


# ── currency ────────────────────────────────────────────────────────────────

def _rate(pair: str = "USD->SAR") -> ExchangeRate:
    return ExchangeRate(
        base="USD", quote="SAR", rate=Decimal("3.75"),
        rate_timestamp=datetime(2026, 3, 1, tzinfo=timezone.utc),
        rate_source="sima_test_fixture",
    )


class TestCurrency:
    def test_sar_amount(self):
        money = normalize_money("1,250.00 SAR")
        assert money.source_amount == Decimal("1250.00")
        assert money.source_currency == "SAR"
        assert money.normalized_amount == Decimal("1250.00")

    def test_currency_is_detected_not_assumed(self):
        money = normalize_money("500.00 USD")
        assert money.source_currency == "USD"
        assert money.source_currency != "SAR"

    def test_no_rate_means_no_conversion(self):
        money = normalize_money("500.00 USD", target_currency="SAR", rates={})
        assert money.normalized_amount is None
        assert money.source_amount == Decimal("500.00")
        assert money.source_currency == "USD"
        assert any("no exchange rate" in n for n in money.notes)

    def test_conversion_with_rate_is_recorded(self):
        money = normalize_money("100.00 USD", target_currency="SAR", rates={"USD->SAR": _rate()})
        assert money.normalized_amount == Decimal("375.0000")
        assert money.exchange_rate == Decimal("3.75")
        assert money.rate_source == "sima_test_fixture"
        assert money.rate_timestamp is not None
        assert money.conversion_method is ConversionMethod.DIRECT_RATE

    def test_bare_amount_does_not_become_sar(self):
        money = normalize_money("1,250.00")
        assert money.source_amount == Decimal("1250.00")
        assert money.normalized_amount is None
        assert money.currency_ambiguous is True
        assert money.is_known is False

    def test_display_keeps_the_real_currency(self):
        money = normalize_money("500.00 USD", target_currency="SAR", rates={})
        assert money.display_currency == "USD"
        assert money.display_value == Decimal("500.00")

    def test_malformed_amount_is_not_zero(self):
        money = normalize_money("about five hundred")
        assert money.source_amount is None
        assert money.normalized_amount is None
        assert money.status == "unknown"

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("1,250.00", Decimal("1250.00")),
            ("SAR 500", Decimal("500")),
            ("(500.00)", Decimal("-500.00")),
            ("-99", Decimal("-99")),
            ("$12.50", Decimal("12.50")),
        ],
    )
    def test_amount_extraction(self, raw, expected):
        assert extract_amount(raw) == expected

    def test_sum_requires_single_currency(self):
        with pytest.raises(IngestionError) as exc:
            sum_money([normalize_money("10.00 SAR"), normalize_money("10.00 USD")])
        assert exc.value.category is ErrorCategory.CURRENCY_ERROR
        assert "mixed currencies" in str(exc.value)

    def test_sum_of_same_currency(self):
        total = sum_money([normalize_money("10.00 SAR"), normalize_money("5.50 SAR")])
        assert total == Decimal("15.50")

    def test_empty_sum_is_none_not_zero(self):
        """An empty sum means 'no evidence', which is not the same as zero."""
        assert sum_money([]) is None

    def test_distinct_currencies_are_visible(self):
        values = [normalize_money("1 SAR"), normalize_money("1 USD")]
        assert distinct_currencies(values) == ("SAR", "USD")

    def test_currency_detection(self):
        assert detect_currency("1,000 SAR") == "SAR"
        assert detect_currency("$1,000") == "USD"
        assert detect_currency("1000") is None

    def test_unknown_target_iso_code_rejected(self):
        """An unrecognised target code must fail loudly, not degrade silently."""
        with pytest.raises(IngestionError) as exc:
            normalize_money("100.00 SAR", target_currency="XTS", rates={})
        assert exc.value.category is ErrorCategory.CURRENCY_ERROR

    def test_unknown_source_iso_code_rejected(self):
        """An unrecognised *declared* source code must fail rather than be dropped."""
        with pytest.raises(IngestionError) as exc:
            normalize_money("100.00", source_currency="XTS")
        assert exc.value.category is ErrorCategory.CURRENCY_ERROR
        assert "ISO 4217" in str(exc.value)

    def test_unrecognised_currency_text_is_not_treated_as_a_code(self):
        """"100 XTS" is not a currency in circulation; it must not become one."""
        money = normalize_money("100 XTS")
        assert money.source_currency is None
        assert money.currency_ambiguous is True
        assert money.normalized_amount is None

    def test_status_transitions(self):
        assert normalize_money("100.00 SAR").status == "source_only"
        assert normalize_money("100.00").status == "currency_unknown"
        assert normalize_money("junk").status == "unknown"
        converted = normalize_money("100.00 USD", target_currency="SAR", rates={"USD->SAR": _rate()})
        assert converted.status == "converted"