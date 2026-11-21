"""Backtrader orchestration for deterministic simulations."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Type

import backtrader as bt
import pandas as pd

from strategies.base_strategy import BaseStrategy
from strategies.ema_crossover import EMACrossoverStrategy
from strategies.rsi_strategy import RSIMeanReversionStrategy
from strategies.sma_crossover import SMACrossoverStrategy

STRATEGIES: dict[str, Type[BaseStrategy]] = {
    "sma": SMACrossoverStrategy, "ema": EMACrossoverStrategy,
    "rsi": RSIMeanReversionStrategy,
}


@dataclass(frozen=True)
class BacktestResult:
    """Serializable result of one deterministic backtest."""

    strategy: str
    initial_cash: float
    final_value: float
    equity_curve: tuple[dict[str, Any], ...]
    orders: tuple[dict[str, Any], ...]
    trades: tuple[dict[str, Any], ...]
    out_of_sample: "BacktestResult | None" = None


class PandasData(bt.feeds.PandasData):
    """Backtrader mapping for validated R-TATS data."""

    params = (("datetime", None), ("open", "Open"), ("high", "High"),
              ("low", "Low"), ("close", "Close"), ("volume", "Volume"),
              ("openinterest", -1))


def run_backtest(
    data: pd.DataFrame,
    strategy: str = "sma",
    initial_cash: float = 10_000.0,
    commission: float = 0.001,
    slippage: float = 0.0,
    strategy_params: dict[str, Any] | None = None,
    *,
    position_size_pct: float = 0.95,
    out_of_sample_data: pd.DataFrame | None = None,
) -> BacktestResult:
    """Run a deterministic event-driven simulation."""
    if strategy not in STRATEGIES:
        raise ValueError(f"Unknown strategy {strategy!r}; choose from {sorted(STRATEGIES)}.")
    if not isfinite(initial_cash) or not isfinite(commission) or not isfinite(slippage):
        raise ValueError("Cash and cost parameters must be finite numeric values.")
    if initial_cash <= 0 or commission < 0 or slippage < 0:
        raise ValueError("Cash must be positive and costs must be non-negative.")
    if not 0 < position_size_pct <= 1:
        raise ValueError("position_size_pct must be greater than 0 and at most 1.")
    frame = data.copy()
    date_column = "Date" if "Date" in frame else "timestamp"
    frame[date_column] = pd.to_datetime(frame[date_column])
    frame = frame.set_index(date_column)
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.adddata(PandasData(dataname=frame))
    params = dict(strategy_params or {})
    params["position_size_pct"] = position_size_pct
    cerebro.addstrategy(STRATEGIES[strategy], **params)
    cerebro.broker.setcash(float(initial_cash))
    cerebro.broker.setcommission(commission=float(commission))
    if slippage:
        cerebro.broker.set_slippage_perc(perc=float(slippage))
    instances = cerebro.run()
    instance = instances[0]
    equity = tuple(instance.equity_curve)
    result = BacktestResult(
        strategy=strategy, initial_cash=float(initial_cash),
        final_value=float(cerebro.broker.getvalue()), equity_curve=equity,
        orders=tuple(instance.order_log), trades=tuple(instance.trade_log),
    )
    if out_of_sample_data is not None:
        oos = run_backtest(
            out_of_sample_data, strategy, initial_cash, commission, slippage,
            strategy_params, position_size_pct=position_size_pct,
        )
        return BacktestResult(
            strategy=result.strategy, initial_cash=result.initial_cash,
            final_value=result.final_value, equity_curve=result.equity_curve,
            orders=result.orders, trades=result.trades, out_of_sample=oos,
        )
    return result
