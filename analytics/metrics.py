"""Deterministic performance analytics with explicit undefined states."""

from __future__ import annotations

from math import isfinite, sqrt
from typing import Any, Sequence

import numpy as np


def calculate_metrics(
    initial_cash: float,
    final_value: float,
    equity_curve: Sequence[dict[str, Any]],
    trades: Sequence[dict[str, Any]],
    *,
    annualization_factor: int = 252,
    risk_free_rate: float = 0.0,
) -> dict[str, Any]:
    """Calculate standard metrics, returning ``None`` for undefined values."""
    try:
        initial_cash = float(initial_cash)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Initial cash must be positive.")
    try:
        annualization_factor = int(annualization_factor)
    except (TypeError, ValueError, OverflowError):
        annualization_factor = 0
    if not isfinite(initial_cash) or initial_cash <= 0:
        raise ValueError("Initial cash must be positive.")
    if annualization_factor <= 0:
        raise ValueError("Annualization factor must be positive.")
    def _safe_row_number(row: Any, keys: tuple[str, ...], fallback: float) -> float:
        if not isinstance(row, dict):
            return fallback
        for key in keys:
            if key in row:
                try:
                    number = float(row[key])
                    if isfinite(number):
                        return number
                except (TypeError, ValueError, OverflowError):
                    pass
        return fallback

    equity_rows = equity_curve if equity_curve is not None else ()
    trade_rows = trades if trades is not None else ()
    values = np.asarray(
        [_safe_row_number(row, ("value", "portfolio_value"), initial_cash)
         for row in equity_rows], dtype=float
    )
    values = values[np.isfinite(values)]
    pnl_values: list[float] = []
    for row in trade_rows:
        if not isinstance(row, dict):
            continue
        if not (
            str(row.get("status", "Closed")).lower() in {"closed", "completed"}
            or "status" not in row
        ):
            continue
        for key in ("pnl_net", "profit_loss"):
            if key in row:
                try:
                    pnl = float(row[key])
                except (TypeError, ValueError, OverflowError):
                    pnl = float("nan")
                if isfinite(pnl):
                    pnl_values.append(pnl)
                break
    pnls = np.asarray(pnl_values, dtype=float)
    pnls = pnls[np.isfinite(pnls)]
    if len(values) > 1:
        previous = values[:-1]
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            returns = np.diff(values) / np.where(previous != 0, previous, np.nan)
        returns = returns[np.isfinite(returns)]
    else:
        returns = np.array([])
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    notes: dict[str, str] = {}
    win_rate = float(len(wins) / len(pnls) * 100) if len(pnls) else None
    if win_rate is None:
        notes["win_rate"] = "Undefined: 0 completed trades"
    profit_factor = float(wins.sum() / abs(losses.sum())) if losses.sum() else None
    if profit_factor is None:
        notes["profit_factor"] = "Undefined: zero gross losses"
    sharpe = None
    if len(returns) >= 2 and float(returns.std(ddof=1)) > 0:
        excess = returns - risk_free_rate / annualization_factor
        sharpe = float(sqrt(annualization_factor) * excess.mean() / returns.std(ddof=1))
    else:
        notes["sharpe_ratio"] = "Undefined: insufficient observations or zero variance"
    if len(values):
        peaks = np.maximum.accumulate(values)
        safe_peaks = np.where(peaks > 0, peaks, np.nan)
        with np.errstate(divide="ignore", invalid="ignore"):
            drawdowns = (peaks - values) / safe_peaks
        drawdowns = drawdowns[np.isfinite(drawdowns)]
        max_drawdown = float(np.max(drawdowns) * 100) if len(drawdowns) else 0.0
    else:
        max_drawdown = 0.0
    try:
        final_value_number = float(final_value)
    except (TypeError, ValueError):
        final_value_number = initial_cash
    if not isfinite(final_value_number):
        final_value_number = initial_cash
    total_change = (final_value_number - initial_cash) / initial_cash * 100
    if not isfinite(total_change):
        total_change = 0.0
    return {
        "total_return": float(total_change),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_drawdown,
        "trade_count": float(len(pnls)),
        "completed_trades": int(len(pnls)),
        "calculation_notes": notes,
    }
