"""Customer-readable post-trade and risk audit report generation."""

from __future__ import annotations

from math import isfinite
from typing import Any, Iterable, Sequence


def _number(value: Any, digits: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if not isfinite(number):
        return "N/A"
    return f"{number:,.{digits}f}"


def _money(value: Any, currency_code: str, currency_symbol: str, digits: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if number != number or number in (float("inf"), float("-inf")):
        return "N/A"
    separator = "" if currency_symbol == "$" else " "
    return f"{currency_symbol}{separator}{number:,.{digits}f} ({currency_code})"


def _closed_trades(trades: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(trades, dict):
        trade_rows = [trades]
    elif isinstance(trades, Iterable) and not isinstance(trades, (str, bytes)):
        trade_rows = [trade for trade in trades if isinstance(trade, dict)]
    else:
        trade_rows = []
    return [
        trade for trade in trade_rows
        if str(trade.get("status", "Closed")).lower() in {"closed", "completed"}
    ]


def _finite_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if isfinite(number) else 0.0


def _finite_int(value: Any) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return int(number) if isfinite(number) and number >= 0 else 0


def _risk_rejections(orders: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    blocked_statuses = {"risk rejected", "canceled", "cancelled", "margin", "rejected"}
    if isinstance(orders, dict):
        order_rows = [orders]
    elif isinstance(orders, Iterable) and not isinstance(orders, (str, bytes)):
        order_rows = [order for order in orders if isinstance(order, dict)]
    else:
        order_rows = []
    return [
        order for order in order_rows
        if str(order.get("status", "")).lower() in blocked_statuses
    ]


def _flat_periods(equity_curve: Sequence[dict[str, Any]]) -> list[tuple[str, str, int]]:
    if isinstance(equity_curve, dict):
        rows = [equity_curve]
    elif isinstance(equity_curve, Iterable) and not isinstance(equity_curve, (str, bytes)):
        rows = [row for row in equity_curve if isinstance(row, dict)]
    else:
        rows = []
    if not rows:
        return []
    periods: list[tuple[str, str, int]] = []
    start = str(rows[0].get("timestamp", rows[0].get("date", "")))
    previous = str(rows[0].get("timestamp", rows[0].get("date", "")))
    previous_value = _finite_float(rows[0].get("value", rows[0].get("portfolio_value", 0)))
    length = 1
    for row in rows[1:]:
        date = str(row.get("timestamp", row.get("date", "")))
        value = _finite_float(row.get("value", row.get("portfolio_value", previous_value)))
        if value == previous_value:
            length += 1
            previous = date
        else:
            if length >= 3:
                periods.append((start, previous, length))
            start = date
            previous = date
            previous_value = value
            length = 1
    if length >= 3:
        periods.append((start, previous, length))
    return periods


def generate_post_trade_risk_report(
    result: Any,
    metrics: dict[str, Any],
    cleaning_actions: Iterable[str] = (),
    commission_percent: float = 0.0,
    slippage_percent: float = 0.0,
    currency_code: str = "USD",
    currency_symbol: str = "$",
    dataset_label: str = "",
    strategy_name: str = "",
    source_row_count: int = 0,
    usable_row_count: int = 0,
) -> str:
    """Generate an audit report without changing simulation data."""
    result_trades = getattr(result, "trades", ()) or ()
    result_orders = getattr(result, "orders", ()) or ()
    result_equity = getattr(result, "equity_curve", ()) or ()
    initial_cash = _finite_float(getattr(result, "initial_cash", 0.0))
    final_value = _finite_float(getattr(result, "final_value", initial_cash))
    if not isinstance(metrics, dict):
        metrics = {}
    try:
        commission_percent = float(commission_percent)
    except (TypeError, ValueError, OverflowError):
        commission_percent = 0.0
    try:
        slippage_percent = float(slippage_percent)
    except (TypeError, ValueError, OverflowError):
        slippage_percent = 0.0
    if not isfinite(commission_percent):
        commission_percent = 0.0
    if not isfinite(slippage_percent):
        slippage_percent = 0.0
    currency_code = str(currency_code or "USD")
    currency_symbol = str(currency_symbol or "$")
    dataset_label = str(dataset_label or "Selected dataset")
    strategy_name = str(strategy_name or getattr(result, "strategy", "sma") or "sma")
    source_row_count = _finite_int(source_row_count)
    usable_row_count = _finite_int(usable_row_count)
    if isinstance(cleaning_actions, str):
        cleaning_actions = (cleaning_actions,)
    elif isinstance(cleaning_actions, dict):
        cleaning_actions = (str(cleaning_actions),)
    elif not isinstance(cleaning_actions, Iterable):
        cleaning_actions = ()

    trades = _closed_trades(result_trades)
    winning = [trade for trade in trades if _finite_float(trade.get("pnl_net", trade.get("profit_loss", 0))) > 0]
    losing = [trade for trade in trades if _finite_float(trade.get("pnl_net", trade.get("profit_loss", 0))) < 0]
    low_margin = [
        trade for trade in trades
        if 0 <= _finite_float(trade.get("pnl_net", trade.get("profit_loss", 0))) <= initial_cash * 0.001
    ]

    strongest = max(
        trades,
        key=lambda trade: _finite_float(trade.get("pnl_net", trade.get("profit_loss", 0))),
        default=None,
    )
    weakest = min(
        trades,
        key=lambda trade: _finite_float(trade.get("pnl_net", trade.get("profit_loss", 0))),
        default=None,
    )
    average_bars = (
        sum(_finite_int(trade.get("bar_length", 0)) for trade in trades) / len(trades)
        if trades else 0.0
    )
    total_net = sum(_finite_float(trade.get("pnl_net", trade.get("profit_loss", 0))) for trade in trades)
    blocked = _risk_rejections(result_orders)
    flats = _flat_periods(result_equity)
    short_trades = sum(
        1 for trade in trades
        if "short" in str(trade.get("side", "")).lower()
    )

    lines = [
        "# Post-Trade & Risk Audit Report",
        "",
        "## Run Parameters",
        f"- Dataset: **{dataset_label}**.",
        f"- Strategy: **{strategy_name.upper()}** (deterministic, long-only simulation).",
        f"- Commission: **{commission_percent:.2f}%** (percentage; applied per execution).",
        f"- Slippage: **{slippage_percent:.2f}%** (percentage; simulated execution friction).",
        f"- Initial capital: **{_money(initial_cash, currency_code, currency_symbol)}** (non-percentage capital units).",
        f"- Total net profit/loss: **{_money(total_net, currency_code, currency_symbol)}** (non-percentage capital units).",
        f"- Final portfolio value: **{_money(final_value, currency_code, currency_symbol)}** (non-percentage capital units).",
        "",
        "## How the Analysis Came to This Result",
        "- OHLCV inputs were normalized, sorted, deduplicated, and screened for malformed values before simulation.",
        "- Signals were evaluated on historical bars and executed only under the configured deterministic strategy and long-only position-sizing rules.",
        f"- Commission and slippage were applied with the configured {commission_percent:.2f}% and {slippage_percent:.2f}% rates.",
        "- Completed trades were summarized using net PnL after commission; KPI values and peak-to-trough drawdown came from the existing deterministic engine.",
        "",
        "## Data Reliability",
        f"- Source rows: **{source_row_count if source_row_count else 'N/A'}**.",
        f"- Usable rows passed into the simulation: **{usable_row_count if usable_row_count else 'N/A'}**.",
        f"- Reliability assessment: **{'High' if usable_row_count >= 100 else 'Limited'}** based on usable row count and post-clean validation.",
        "- Reliability does not guarantee future performance; results are historical simulation outputs only.",
        "",
        "## What Worked",
        f"- {len(winning)} profitable trade(s) from {len(trades)} completed trade(s).",
        f"- Total net PnL after commission and slippage: **{_money(total_net, currency_code, currency_symbol)}**.",
        f"- Average holding period: **{average_bars:.2f} bar(s)**.",
    ]
    if strongest is not None:
        lines.append(
            f"- Strongest trade: **{strongest.get('entry_time', 'N/A')} to "
            f"{strongest.get('exit_time', 'N/A')}**, net PnL "
            f"**{_money(strongest.get('pnl_net', strongest.get('profit_loss', 0)), currency_code, currency_symbol)}** "
            f"on {_number(strongest.get('quantity', 0), 2)} unit(s)."
        )
    else:
        lines.append("- No profitable trade was available to rank.")

    lines.extend([
        "",
        "## What Didn't",
        f"- Losing trades: **{len(losing)}**.",
        f"- Low-margin trades (net PnL between 0 and 0.1% of initial capital): **{len(low_margin)}**.",
        f"- SHORT trades: **{short_trades}**. The R-TATS execution engine is long-only (`LONG` entries and closes); no SHORT positions are opened.",
    ])
    if weakest is not None:
        lines.append(
            f"- Weakest completed trade: **{weakest.get('entry_time', 'N/A')} to "
            f"{weakest.get('exit_time', 'N/A')}**, net PnL "
            f"**{_money(weakest.get('pnl_net', weakest.get('profit_loss', 0)), currency_code, currency_symbol)}**."
        )
    drawdown = metrics.get("max_drawdown")
    lines.append(f"- Peak-to-trough maximum drawdown: **{_number(drawdown)}%**.")
    if flats:
        descriptions = ", ".join(
            f"{start} to {end} ({length} bars)" for start, end, length in flats
        )
        lines.append(f"- Flat or idle equity periods: {descriptions}.")
    else:
        lines.append("- No extended flat equity period (3 or more consecutive unchanged bars) was detected.")

    if commission_percent >= 20.0 or slippage_percent >= 20.0:
        lines.extend([
            "",
            "## High-Cost Stress Test",
            "- **Stress-test note:** 20% or higher commission/slippage was applied.",
            "- The high-cost setting may significantly erode net PnL and returns; results are deterministic simulation outputs.",
        ])

    lines.extend(["", "## Executed Buys & Sells", "", "| Side | Entry | Exit | Quantity | Entry Price | Exit Price | Commission | Net PnL | Status |"])
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---|")
    if trades:
        for trade in trades:
            lines.append(
                "| LONG entry / closed exit "
                f"| {trade.get('entry_time', 'N/A')} | {trade.get('exit_time', 'N/A')} "
                f"| {_number(trade.get('quantity', 0), 4)} "
                f"| {_money(trade.get('entry_price', 0), currency_code, currency_symbol, 4)} "
                f"| {_money(trade.get('exit_price', 0), currency_code, currency_symbol, 4)} "
                f"| {_money(trade.get('commission', 0), currency_code, currency_symbol, 4)} "
                f"| {_money(trade.get('pnl_net', trade.get('profit_loss', 0)), currency_code, currency_symbol, 4)} "
                f"| {trade.get('status', 'Closed')} |"
            )
    else:
        lines.append("| No executed trades | - | - | - | - | - | - | - | - |")

    lines.extend(["", "## Risk Check Rejections & Data Hygiene", ""])
    if blocked:
        lines.append(f"- {len(blocked)} order(s) blocked or rejected:")
        for order in blocked:
            lines.append(
                f"  - Bar/date {order.get('date', order.get('timestamp', 'N/A'))}: "
                f"{order.get('status', 'Rejected')} - "
                f"{order.get('reason', 'Order canceled, margin-constrained, or rejected by the broker.')}"
            )
    else:
        lines.append("- `0 orders blocked by risk checks`")
    actions = [str(action) for action in cleaning_actions if str(action)]
    detected = [action for action in actions if action.startswith("Issue detected:")]
    modifications = [action for action in actions if action.startswith("Cleaning action:")]
    legacy_modifications = [
        action for action in actions
        if not action.startswith(("Issue detected:", "Post-clean", "Cleaning action:"))
        and not action.startswith("Extraction/cleaning count:")
        and action not in {"No compatibility issues were detected.", "The dataset was inspected; no rows required removal."}
        and not action.startswith("Post-clean ")
    ]
    modifications.extend(legacy_modifications)
    post_checks = [action for action in actions if action.startswith("Post-clean")]
    extraction_counts = [action for action in actions if action.startswith("Extraction/cleaning count:")]
    if detected:
        lines.append("- Compatibility issues detected:")
        lines.extend(f"  - {action.removeprefix('Issue detected: ').strip()}" for action in detected)
    if modifications:
        lines.append("- Auto-cleaning actions applied:")
        lines.extend(f"  - {action.removeprefix('Cleaning action: ').strip()}" for action in modifications)
    else:
        lines.append("- Data hygiene: no auto-cleaning actions were applied.")
    if post_checks:
        lines.append("- Post-clean verification:")
        lines.extend(f"  - {action}" for action in post_checks)
    if extraction_counts:
        lines.append("- Data extraction/cleaning counts:")
        lines.extend(f"  - {action.removeprefix('Extraction/cleaning count: ').strip()}" for action in extraction_counts)
    return "\n".join(lines)
