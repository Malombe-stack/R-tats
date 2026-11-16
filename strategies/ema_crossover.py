"""Exponential moving-average crossover strategy."""

from __future__ import annotations

import backtrader as bt

from strategies.base_strategy import BaseStrategy


class EMACrossoverStrategy(BaseStrategy):
    """Buy on a fast-EMA cross above a slow EMA and exit on reverse."""

    params = (("fast_period", 10), ("slow_period", 30))

    def __init__(self) -> None:
        if not isinstance(self.p.fast_period, int) or self.p.fast_period <= 0:
            raise ValueError("fast_period must be a positive integer.")
        if not isinstance(self.p.slow_period, int) or self.p.slow_period <= self.p.fast_period:
            raise ValueError("slow_period must be an integer greater than fast_period.")
        super().__init__()
        self.fast = bt.indicators.ExponentialMovingAverage(self.data.close, period=self.p.fast_period)
        self.slow = bt.indicators.ExponentialMovingAverage(self.data.close, period=self.p.slow_period)
        self.crossover = bt.indicators.CrossOver(self.fast, self.slow)

    def next(self) -> None:
        """Evaluate the closed bar and submit next-bar orders."""
        self.record_equity()
        if self.order:
            return
        if not self.position and self.crossover > 0 and self.position_size() > 0:
            self.order = self.buy(size=self.position_size())
        elif self.position and self.crossover < 0:
            self.order = self.close()
