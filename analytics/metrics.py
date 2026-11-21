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
    if initial_cash <= 0:
        raise ValueError("Initial cash must be positive.")
    if annualization_factor <= 0:
        raise ValueError("Annualization factor must be positive.")
    values = np.asarray(
        [float(row.get("value", row.get("portfolio_value", initial_cash)))
         for row in equity_curve], dtype=float
    )
    values = values[np.isfinite(values)]
    pnls = np.asarray(
        [float(row.get("pnl_net", row.get("profit_loss", 0.0)))
         for row in trades
         if str(row.get("status", "Closed")).lower() in {"closed", "completed"}
         or "status" not in row],
        dtype=float,
    )
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
    total_change = (final_value - initial_cash) / initial_cash * 100
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
