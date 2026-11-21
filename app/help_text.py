"""Direct help-text and unit metadata for R-TATS interface controls."""

from __future__ import annotations


HELP = {
    "upload": "Upload OHLCV CSV data. Fields are percentages/non-percentages as labeled.",
    "dataset": "Dataset: a non-percentage historical data source containing dated OHLCV bars.",
    "strategy": "Strategy: SMA, EMA, or RSI determines entry/exit signals; it does not change KPI formulas.",
    "initial_capital": "Initial capital (non-percentage): starting simulated portfolio currency/capital units; NSE uses KES/KSh and US markets use USD/$.",
    "commission": "Commission (%) (percentage): execution cost deducted for buys and sells.",
    "slippage": "Slippage (%) (percentage): simulated adverse execution price impact.",
    "position_size": "Position size (%) (percentage): cash percentage allocated to an eligible buy.",
    "fast_period": "Fast period (non-percentage bars): shorter SMA/EMA lookback.",
    "slow_period": "Slow period (non-percentage bars): longer SMA/EMA lookback.",
    "rsi_period": "RSI period (non-percentage bars): lookback used by the RSI indicator.",
    "oversold": "Oversold (%) (percentage threshold): buys near this RSI threshold.",
    "overbought": "Overbought (%) (percentage threshold): closes near this RSI threshold.",
    "sma": "SMA (non-percentage price average): simple moving average over a bar count.",
    "ema": "EMA (non-percentage price average): exponentially weighted moving average.",
    "rsi": "RSI (percentage index): 0-100 momentum threshold used for entries/exits.",
    "total_return": "Total Return (%): percentage change from initial capital to final portfolio value.",
    "sharpe_ratio": "Sharpe Ratio (non-percentage risk-adjusted ratio): excess return per unit of volatility.",
    "max_drawdown": "Max Drawdown (%): peak-to-trough percentage decline of the equity curve.",
    "win_rate": "Win Rate (%): percentage of completed trades with positive pnl_net.",
    "profit_factor": "Profit Factor (non-percentage ratio): gross winning PnL divided by absolute gross losing PnL.",
    "completed_trades": "Completed Trades (non-percentage integer count): number of closed round-trip trades.",
    "equity_curve": "Equity Curve (non-percentage capital values over dates): portfolio value after each bar.",
    "pnl": "PnL (non-percentage profit/loss amount): gross trade profit/loss before net commission adjustments.",
    "pnl_net": "pnl_net (non-percentage profit/loss amount): PnL after commission; used for winning/losing classification.",
    "bar_length": "bar_length (non-percentage integer count): holding duration in bars.",
    "risk_checks": "Risk checks: blocked/rejected orders by capital, sizing, margin, or broker constraints.",
    "long_only": (
        "Long-only execution (non-percentage scope/count): R-TATS opens LONG positions "
        "and closes them; it does not execute SHORT trades. Quantity is the number of "
        "shares or units bought and is not a percentage."
    ),
    "commission_field": "commission (non-percentage currency amount): total execution commission for a trade in the active market currency.",
    "entry_time": "entry_time (non-percentage timestamp): date the LONG position opened.",
    "exit_time": "exit_time (non-percentage timestamp): date the position closed.",
    "quantity": "quantity (non-percentage share/unit count): number of shares or units bought or traded.",
    "entry_price": "entry_price (non-percentage currency/price): execution price at entry in the active market currency.",
    "exit_price": "exit_price (non-percentage currency/price): execution price at exit in the active market currency.",
}


def tooltip(name: str) -> str:
    """Return a known definition or a safe, labeled fallback for UI metadata."""
    if name in HELP:
        return HELP[name]
    readable_name = str(name).replace("_", " ").strip()
    label = readable_name.title() if readable_name else "This item"
    return (
        f"{label} (non-percentage by default if unit type is unknown): "
        "additional information is not currently available."
    )
