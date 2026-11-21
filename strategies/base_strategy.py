"""Shared Backtrader strategy behavior."""

from __future__ import annotations

from typing import Any

import backtrader as bt


class BaseStrategy(bt.Strategy):
    """Base strategy with next-bar execution and structured logs."""

    params = (("stake", 0.0), ("position_size_pct", 0.95))

    def __init__(self) -> None:
        if self.p.position_size_pct <= 0 or self.p.position_size_pct > 1:
            raise ValueError("position_size_pct must be greater than 0 and at most 1.")
        if self.p.stake < 0:
            raise ValueError("stake must be non-negative.")
        self.order: bt.Order | None = None
        self.order_log: list[dict[str, Any]] = []
        self.trade_log: list[dict[str, Any]] = []
        self.equity_curve: list[dict[str, Any]] = []
        self._entry_quantity = 0.0
        self._entry_price = 0.0
        self._entry_time = ""

    def position_size(self) -> float:
        """Return a cash-safe integer position size."""
        if self.p.stake:
            return float(self.p.stake)
        price = float(self.data.close[0])
        return float(int(self.broker.getcash() * self.p.position_size_pct / price))

    def record_risk_rejection(self, reason: str) -> None:
        """Record a signal blocked before an order is submitted."""
        date = self.data.datetime.date(0).isoformat()
        self.order_log.append({
            "date": date, "timestamp": date,
            "side": "BUY", "status": "Risk Rejected", "reason": reason,
        })

    def notify_order(self, order: bt.Order) -> None:
        """Record completed, cancelled, or rejected orders."""
        if order.status in (order.Submitted, order.Accepted):
            return
        status = order.getstatusname()
        date = self.data.datetime.date(0).isoformat()
        if order.status == order.Completed:
            if order.isbuy():
                self._entry_quantity = float(abs(order.executed.size))
                self._entry_price = float(order.executed.price)
                self._entry_time = date
            self.order_log.append({
                "date": date, "timestamp": date,
                "side": "BUY" if order.isbuy() else "SELL",
                "price": float(order.executed.price),
                "size": float(order.executed.size),
                "quantity": float(order.executed.size),
                "commission": float(order.executed.comm), "status": status,
            })
        elif order.status in (order.Canceled, order.Margin, order.Rejected):
            self.order_log.append({"date": date, "status": status})
        self.order = None

    def notify_trade(self, trade: bt.Trade) -> None:
        """Record each completed round-trip trade."""
        if trade.isclosed:
            entry = self._entry_time or self.data.datetime.date(-trade.barlen).isoformat()
            exit_time = self.data.datetime.date(0).isoformat()
            self.trade_log.append({
                "entry_time": entry, "exit_time": exit_time, "side": "LONG",
                "quantity": self._entry_quantity, "entry_price": self._entry_price,
                "exit_price": float(self.data.close[0]),
                "commission": float(trade.commission),
                "profit_loss": float(trade.pnlcomm), "pnl": float(trade.pnl),
                "pnl_net": float(trade.pnlcomm), "status": "Closed",
                "bar_length": int(trade.barlen),
            })

    def record_equity(self) -> None:
        """Record end-of-bar portfolio state."""
        date = self.data.datetime.date(0).isoformat()
        value = float(self.broker.getvalue())
        self.equity_curve.append({
            "timestamp": date, "date": date, "portfolio_value": value,
            "value": value, "cash": float(self.broker.getcash()),
        })
