"""RSI mean-reversion strategy."""

from __future__ import annotations

import backtrader as bt

from strategies.base_strategy import BaseStrategy


class RSIMeanReversionStrategy(BaseStrategy):
    """Buy below oversold and exit above overbought."""

    params = (("rsi_period", 14), ("oversold", 30.0), ("overbought", 70.0))

    def __init__(self) -> None:
        if not isinstance(self.p.rsi_period, int) or self.p.rsi_period <= 1:
            raise ValueError("rsi_period must be an integer greater than 1.")
        if not 0 < self.p.oversold < 50:
            raise ValueError("oversold must be between 0 and 50.")
        if not 50 < self.p.overbought < 100 or self.p.overbought <= self.p.oversold:
            raise ValueError("overbought must be between 50 and 100.")
        super().__init__()
        self.rsi = bt.indicators.RelativeStrengthIndex(
            self.data.close, period=self.p.rsi_period, safediv=True
        )

    def next(self) -> None:
        """Evaluate the closed bar and submit next-bar orders."""
        self.record_equity()
        if self.order:
            return
        if not self.position and self.rsi < self.p.oversold:
            size = self.position_size()
            if size > 0:
                self.order = self.buy(size=size)
            else:
                self.record_risk_rejection("Position size is zero: insufficient capital or price constraint.")
        elif self.position and self.rsi > self.p.overbought:
            self.order = self.close()


RSIStrategy = RSIMeanReversionStrategy
