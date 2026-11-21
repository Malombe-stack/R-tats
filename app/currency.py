"""Market-aware display currency resolution for R-TATS."""

from __future__ import annotations

import re


def resolve_market_currency(*sources: object) -> tuple[str, str]:
    """Return (code, display symbol) for NSE/KES and otherwise USD."""
    text = " ".join(str(source) for source in sources if source).upper()
    nse_marker = bool(re.search(r"(?:^|[^A-Z])NSE(?:[^A-Z]|$)", text))
    nse_ticker = bool(re.search(r"(?:^|[./_-])(?:[A-Z0-9-]+\.NR)(?:[^A-Z0-9]|$)", text))
    if nse_marker or ".NR" in text or "NSE_" in text:
        return "KES", "KSh"
    if nse_ticker:
        return "KES", "KSh"
    return "USD", "$"


def format_currency(value: object, symbol: str, digits: int = 2) -> str:
    """Format a numeric currency value without changing the underlying value."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if not (number == number) or number in (float("inf"), float("-inf")):
        return "N/A"
    separator = "" if symbol == "$" else " "
    return f"{symbol}{separator}{number:,.{digits}f}"
