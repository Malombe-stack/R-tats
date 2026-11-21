"""Customer-readable post-trade and risk audit report generation."""

from __future__ import annotations

from typing import Any, Iterable, Sequence


def _number(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "N/A"


def _closed_trades(trades: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [trade for trade in trades if str(trade.get("status", "Closed")).lower() in {"closed", "completed"}]


def _risk_rejections(orders: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    blocked_statuses = {"risk rejected", "canceled", "cancelled", "margin", "rejected"}
    return [
        order for order in orders
        if str(order.get("status", "")).lower() in blocked_statuses
    ]


def _flat_periods(equity_curve: Sequence[dict[str, Any]]) -> list[tuple[str, str, int]]:
    if not equity_curve:
        return []
    periods: list[tuple[str, str, int]] = []
    start = str(equity_curve[0].get("timestamp", equity_curve[0].get("date", "")))
    previous = str(equity_curve[0].get("timestamp", equity_curve[0].get("date", "")))
    previous_value = float(equity_curve[0].get("value", equity_curve[0].get("portfolio_value", 0)))
    length = 1
    for row in equity_curve[1:]:
        date = str(row.get("timestamp", row.get("date", "")))
        value = float(row.get("value", row.get("portfolio_value", previous_value)))
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
) -> str:
    """Generate a Markdown audit report without changing simulation data."""
    trades = _closed_trades(result.trades)
    winning = [trade for trade in trades if float(trade.get("pnl_net", trade.get("profit_loss", 0))) > 0]
    losing = [trade for trade in trades if float(trade.get("pnl_net", trade.get("profit_loss", 0))) < 0]
    low_margin = [
        trade for trade in trades
        if 0 <= float(trade.get("pnl_net", trade.get("profit_loss", 0))) <= result.initial_cash * 0.001
    ]

    strongest = max(
        trades,
        key=lambda trade: float(trade.get("pnl_net", trade.get("profit_loss", 0))),
        default=None,
    )
    weakest = min(
        trades,
        key=lambda trade: float(trade.get("pnl_net", trade.get("profit_loss", 0))),
        default=None,
    )
    average_bars = (
        sum(int(trade.get("bar_length", 0)) for trade in trades) / len(trades)
        if trades else 0.0
    )
    total_net = sum(float(trade.get("pnl_net", trade.get("profit_loss", 0))) for trade in trades)
    blocked = _risk_rejections(result.orders)
    flats = _flat_periods(result.equity_curve)

    lines = [
        "# Post-Trade & Risk Audit Report",
        "",
        "## What Worked",
        f"- {len(winning)} profitable trade(s) from {len(trades)} completed trade(s).",
        f"- Total net profit after commission: **{_number(total_net)}**.",
        f"- Average holding period: **{average_bars:.2f} bar(s)**.",
    ]
    if strongest is not None:
        lines.append(
            f"- Strongest trade: **{strongest.get('entry_time', 'N/A')} to "
            f"{strongest.get('exit_time', 'N/A')}**, net PnL "
            f"**{_number(strongest.get('pnl_net', strongest.get('profit_loss', 0)))}** "
            f"on {_number(strongest.get('quantity', 0), 2)} unit(s)."
        )
    else:
        lines.append("- No profitable trade was available to rank.")

    lines.extend([
        "",
        "## What Didn't",
        f"- Losing trades: **{len(losing)}**.",
        f"- Low-margin trades (net PnL between 0 and 0.1% of initial capital): **{len(low_margin)}**.",
    ])
    if weakest is not None:
        lines.append(
            f"- Weakest completed trade: **{weakest.get('entry_time', 'N/A')} to "
            f"{weakest.get('exit_time', 'N/A')}**, net PnL "
            f"**{_number(weakest.get('pnl_net', weakest.get('profit_loss', 0)))}**."
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

    lines.extend(["", "## Executed Buys & Sells", "", "| Side | Entry | Exit | Quantity | Entry Price | Exit Price | Commission | Net PnL | Status |"])
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---|")
    if trades:
        for trade in trades:
            lines.append(
                "| LONG entry / closed exit "
                f"| {trade.get('entry_time', 'N/A')} | {trade.get('exit_time', 'N/A')} "
                f"| {_number(trade.get('quantity', 0), 4)} "
                f"| {_number(trade.get('entry_price', 0), 4)} "
                f"| {_number(trade.get('exit_price', 0), 4)} "
                f"| {_number(trade.get('commission', 0), 4)} "
                f"| {_number(trade.get('pnl_net', trade.get('profit_loss', 0)), 4)} "
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
    if actions:
        lines.append("- Auto-cleaning actions:")
        lines.extend(f"  - {action}" for action in actions)
    else:
        lines.append("- Data hygiene: no auto-cleaning actions were applied.")
    return "\n".join(lines)
