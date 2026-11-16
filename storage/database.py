"""SQLite persistence for simulation runs."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any


class RunRepository:
    """Repository implementing the R-TATS relational persistence schema."""

    def __init__(self, path: str | Path) -> None:
        self.connection = sqlite3.connect(Path(path))
        self.connection.row_factory = sqlite3.Row
        self.initialize()

    def initialize(self) -> None:
        """Create all persistence tables and indexes."""
        self.connection.executescript("""
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS backtest_runs (
          run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, dataset_name TEXT NOT NULL,
          instrument TEXT NOT NULL, frequency TEXT NOT NULL, start_date TEXT,
          end_date TEXT, strategy_name TEXT NOT NULL, parameters_json TEXT NOT NULL,
          initial_capital REAL NOT NULL, cost_assumptions_json TEXT NOT NULL,
          status TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS run_metrics (
          metric_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
          metric_name TEXT NOT NULL, metric_value REAL NULL, calculation_notes TEXT,
          FOREIGN KEY(run_id) REFERENCES backtest_runs(run_id)
        );
        CREATE TABLE IF NOT EXISTS simulated_trades (
          trade_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
          entry_time TEXT, exit_time TEXT, side TEXT, quantity REAL,
          entry_price REAL, exit_price REAL, commission REAL, profit_loss REAL,
          status TEXT, FOREIGN KEY(run_id) REFERENCES backtest_runs(run_id)
        );
        CREATE TABLE IF NOT EXISTS dataset_metadata (
          dataset_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
          source TEXT, instrument TEXT, frequency TEXT, date_range TEXT,
          import_time TEXT NOT NULL, validation_summary TEXT
        );
        """)
        self.connection.commit()

    def save_run(
        self,
        result: Any,
        metrics: dict[str, Any],
        *,
        dataset_name: str = "dataset",
        instrument: str = "",
        frequency: str = "Daily",
        parameters: dict[str, Any] | None = None,
        cost_assumptions: dict[str, Any] | None = None,
    ) -> str:
        """Persist a result and return its UUID run identifier."""
        run_id = str(uuid.uuid4())
        curve = result.equity_curve
        start = curve[0].get("timestamp") if curve else None
        end = curve[-1].get("timestamp") if curve else None
        self.connection.execute(
            """INSERT INTO backtest_runs VALUES (?, datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, dataset_name, instrument, frequency, start, end,
             result.strategy, json.dumps(parameters or {}, sort_keys=True),
             result.initial_cash, json.dumps(cost_assumptions or {}, sort_keys=True),
             "completed"),
        )
        notes = metrics.get("calculation_notes", {})
        self.connection.executemany(
            "INSERT INTO run_metrics(run_id, metric_name, metric_value, calculation_notes) VALUES (?, ?, ?, ?)",
            [(run_id, name, value if isinstance(value, (int, float)) else None,
              notes.get(name, "")) for name, value in metrics.items()
             if name != "calculation_notes"],
        )
        self.connection.executemany(
            """INSERT INTO simulated_trades
            (run_id, entry_time, exit_time, side, quantity, entry_price, exit_price,
             commission, profit_loss, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(run_id, t.get("entry_time"), t.get("exit_time"), t.get("side"),
              t.get("quantity"), t.get("entry_price"), t.get("exit_price"),
              t.get("commission"), t.get("profit_loss", t.get("pnl_net")),
              t.get("status", "Closed")) for t in result.trades],
        )
        self.connection.commit()
        return run_id

    def close(self) -> None:
        """Close the database connection."""
        self.connection.close()
