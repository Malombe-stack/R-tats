"""Streamlit dashboard for the R-TATS academic simulation."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import plotly.graph_objects as go
import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analytics.metrics import calculate_metrics
from backtesting.runner import run_backtest
from ingestion.loader import load_csv

DISCLAIMER = (
    "Simulation only: results are simulated historical evaluations and do not "
    "guarantee future returns. No live trading is supported."
)
DATA_DIR = PROJECT_ROOT / "data"
SAMPLES_DIR = DATA_DIR / "samples"
PROCESSED_DIR = DATA_DIR / "processed"
DATA_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def _metric_text(value: Any, notes: dict[str, str], name: str) -> str:
    """Render a metric while preserving an explicit undefined explanation."""
    if value is None:
        return f"N/A — {notes.get(name, 'undefined')}"
    return f"{value:.4f}"


def _instrument_from_filename(path: Path) -> str:
    """Infer a display instrument code from a bundled dataset filename."""
    name = re.sub(r"_(?:\d+Y|SAMPLE)_DAILY$", "", path.stem)
    return name.replace("_NR", ".NR")


def main() -> None:
    """Render the dashboard."""
    st.set_page_config(page_title="R-TATS", layout="wide")
    st.title("R-TATS — STU 3101 Quantitative Simulation")
    st.warning(DISCLAIMER)
    with st.sidebar:
        st.header("Simulation configuration")
        uploaded = st.file_uploader("Upload OHLCV CSV", type="csv")
        bundled_paths = sorted(SAMPLES_DIR.glob("*.csv"))
        selected_path = st.selectbox(
            "Bundled dataset",
            bundled_paths,
            format_func=lambda path: path.name,
            disabled=not bundled_paths,
        )
        instrument = (
            _instrument_from_filename(selected_path)
            if selected_path and uploaded is None
            else ""
        )
        strategy = st.selectbox("Strategy", ["sma", "ema", "rsi"])
        initial_cash = st.number_input("Initial capital", min_value=1.0, value=10000.0)
        commission = st.number_input("Commission (%)", min_value=0.0, value=0.1) / 100
        slippage = st.number_input("Slippage (%)", min_value=0.0, value=0.05) / 100
        position_size_pct = st.number_input(
            "Position size (%)", min_value=1.0, max_value=100.0, value=95.0
        ) / 100
        if strategy in {"sma", "ema"}:
            fast = st.number_input("Fast period", min_value=1, value=10)
            slow = st.number_input("Slow period", min_value=2, value=30)
            parameters = {"fast_period": fast, "slow_period": slow}
        else:
            period = st.number_input("RSI period", min_value=2, value=14)
            oversold = st.number_input("Oversold", min_value=0.1, max_value=49.9, value=30.0)
            overbought = st.number_input("Overbought", min_value=50.1, max_value=99.9, value=70.0)
            parameters = {
                "rsi_period": period, "oversold": oversold, "overbought": overbought
            }
        run = st.button("Run Backtest", type="primary")
    if not run:
        st.info("Choose a dataset and configuration, then run the simulation.")
        return
    try:
        if uploaded is not None:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as handle:
                handle.write(uploaded.getvalue())
                source = handle.name
        else:
            source = selected_path
        data, metadata = load_csv(source, instrument=instrument)
        result = run_backtest(
            data, strategy, initial_cash, commission, slippage, parameters,
            position_size_pct=position_size_pct,
        )
        metrics = calculate_metrics(
            result.initial_cash, result.final_value, result.equity_curve, result.trades
        )
    except (OSError, ValueError) as error:
        st.error(str(error))
        return
    st.caption(
        f"{metadata.source or 'dataset'} | {metadata.start_date} to {metadata.end_date} | "
        f"{metadata.row_count} rows | {strategy}"
    )
    notes = metrics["calculation_notes"]
    columns = st.columns(6)
    for column, name in zip(
        columns,
        ("total_return", "sharpe_ratio", "max_drawdown", "win_rate", "profit_factor", "completed_trades"),
    ):
        column.metric(name.replace("_", " ").title(), _metric_text(metrics[name], notes, name))
    equity = pd.DataFrame(result.equity_curve) if result.equity_curve else None
    if equity is not None:
        figure = go.Figure(go.Scatter(x=equity["timestamp"], y=equity["value"], name="Equity"))
        figure.add_hline(y=result.initial_cash, line_dash="dash", name="Initial capital")
        st.plotly_chart(figure, use_container_width=True)
    st.subheader("Simulated trade log")
    st.dataframe(result.trades)


if __name__ == "__main__":
    main()
