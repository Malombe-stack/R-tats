"""Tests for stress-cost execution and percentage/non-percentage help metadata."""

import math

from app.help_text import HELP, tooltip
from backtesting.runner import run_backtest
from analytics.metrics import calculate_metrics


def test_extreme_20_percent_commission_and_slippage_are_finite(valid_data) -> None:
    result = run_backtest(
        valid_data,
        "sma",
        initial_cash=10000.0,
        commission=0.20,
        slippage=1.00,
        position_size_pct=0.95,
    )
    metrics = calculate_metrics(
        result.initial_cash,
        result.final_value,
        result.equity_curve,
        result.trades,
    )

    assert math.isfinite(result.final_value)
    assert all(math.isfinite(float(row["value"])) for row in result.equity_curve)
    assert all(
        math.isfinite(float(value))
        for key, value in metrics.items()
        if key != "calculation_notes" and value is not None
    )


def test_percentage_and_non_percentage_definitions_are_explicit() -> None:
    assert "%)" not in HELP["initial_capital"]
    assert "(non-percentage" in HELP["initial_capital"]
    assert "(percentage)" in HELP["commission"]
    assert "Total Return (%)" in tooltip("total_return")
    assert "Sharpe Ratio (non-percentage risk-adjusted ratio)" in tooltip("sharpe_ratio")
    assert "Max Drawdown (%)" in tooltip("max_drawdown")
    assert "Win Rate (%)" in tooltip("win_rate")
    assert "Completed Trades (non-percentage integer count)" in tooltip("completed_trades")
