"""Money helpers for exact SAR arithmetic.

Use Decimal for all monetary calculations. Convert to float/string only at API/JSON
boundaries where required by existing schemas.
"""
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any

SAR_QUANT = Decimal("0.01")


def decimal_value(value: Any, default: str = "0") -> Decimal:
    if value is None or value == "":
        value = default
    return Decimal(str(value))


def sar(value: Any) -> Decimal:
    return decimal_value(value).quantize(SAR_QUANT, rounding=ROUND_HALF_EVEN)


def sar_float(value: Any) -> float:
    return float(sar(value))


def sar_str(value: Any) -> str:
    return f"{sar(value):.2f}"
