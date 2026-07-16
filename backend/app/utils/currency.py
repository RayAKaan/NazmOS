def format_inr(amount: float) -> str:
    if amount >= 10000000:
        return f"﷼ {amount / 10000000:.2f}Cr"
    elif amount >= 100000:
        return f"﷼ {amount / 100000:.2f}L"
    elif amount >= 1000:
        return f"﷼ {amount / 1000:.1f}K"
    else:
        return f"﷼ {amount:.0f}"


def format_inr_full(amount: float) -> str:
    return f"﷼ {amount:,.0f}"


def parse_inr(text: str) -> float | None:
    import re
    match = re.search(r"﷼ ?\s*([\d,.]+)", text.replace(",", ""))
    if match:
        return float(match.group(1))
    return None
