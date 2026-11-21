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
from analytics.post_trade_report import generate_post_trade_risk_report
from backtesting.runner import run_backtest
from ingestion.cleaner import CleaningResult, clean_ohlcv_csv
from ingestion.loader import load_csv
from ingestion.validator import extract_metadata, validate_ohlcv

DISCLAIMER = (
    "Simulation only: results are simulated historical evaluations and do not "
    "guarantee future returns. No live trading is supported."
)
DATA_DIR = PROJECT_ROOT / "data"
SAMPLES_DIR = DATA_DIR / "samples"
PROCESSED_DIR = DATA_DIR / "processed"
DATA_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

APP_CSS = """
<style>
.block-container {max-width: 1180px; padding-top: 1.5rem;}
[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #dfe6ef;
    border-radius: 12px;
    padding: 14px 16px;
    box-shadow: 0 2px 10px rgba(23, 32, 51, 0.05);
}
[data-testid="stMetricLabel"], [data-testid="stMetricValue"] {
    font-variant-numeric: tabular-nums;
    white-space: normal;
}
[data-testid="stMetricValue"] {font-size: 1.45rem; overflow-wrap: anywhere;}
.rt-header {border-bottom: 1px solid #dfe6ef; padding-bottom: 0.75rem; margin-bottom: 0.35rem;}
.rt-header h1 {margin-bottom: 0.15rem;}
.rt-subtitle {color: #526176; font-size: 1.05rem; margin-bottom: 0.35rem;}
.rt-mode {
    display: inline-block; background: #e8f0ff; color: #1d4ed8;
    border: 1px solid #bfdbfe; border-radius: 999px;
    padding: 0.18rem 0.55rem; font-size: 0.82rem; font-weight: 700;
}
.rt-section {margin-top: 0.25rem;}
</style>
"""


def _metric_text(value: Any, notes: dict[str, str], name: str) -> str:
    """Render a metric while preserving an explicit undefined explanation."""
    if value is None:
        return f"N/A — {notes.get(name, 'undefined')}"
    return f"{value:.4f}"


def _instrument_from_filename(path: Path) -> str:
    """Infer a display instrument code from a bundled dataset filename."""
    name = re.sub(r"_(?:\d+Y|SAMPLE)_DAILY$", "", path.stem)
    return name.replace("_NR", ".NR")


def _kpi_value(value: Any, name: str) -> str:
    if value is None:
        return "N/A"
    if name in {"total_return", "max_drawdown", "win_rate"}:
        return f"{float(value):.2f}%"
    if name in {"sharpe_ratio", "profit_factor"}:
        return f"{float(value):.2f}"
    return f"{int(value):,}"


def _cleaned_csv_bytes(cleaned: pd.DataFrame) -> bytes:
    return cleaned.to_csv(index=False).encode("utf-8")


def main() -> None:
    """Render the dashboard."""
    st.set_page_config(
        page_title="R-TATS",
        page_icon="R",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(APP_CSS, unsafe_allow_html=True)
    st.markdown(
        '<div class="rt-header"><h1>R-TATS</h1>'
        '<div class="rt-subtitle">Deterministic historical backtesting and post-trade risk intelligence</div>'
        '<span class="rt-mode">Simulation Mode</span></div>',
        unsafe_allow_html=True,
    )
    st.warning(DISCLAIMER)
    uploaded_cleaning: CleaningResult | None = None
    with st.sidebar:
        st.header("Simulation Configuration")
        st.caption("Upload OHLCV data or use a bundled deterministic dataset.")
        uploaded = st.file_uploader("Upload OHLCV CSV", type="csv")
        if uploaded is not None:
            uploaded_cleaning = clean_ohlcv_csv(uploaded.getvalue())
            if uploaded_cleaning.issues:
                st.error("CSV compatibility issues detected")
                for issue in uploaded_cleaning.issues:
                    st.write(f"- {issue}")
                st.caption("Cleaning summary")
                for action in uploaded_cleaning.actions:
                    st.write(f"- {action}")
                if uploaded_cleaning.data.empty:
                    st.warning("Required columns are missing or no usable rows remain.")
                else:
                    st.download_button(
                        "Download cleaned CSV",
                        data=_cleaned_csv_bytes(uploaded_cleaning.data),
                        file_name="r_tats_cleaned.csv",
                        mime="text/csv",
                        key="cleaned_csv_download",
                    )
            else:
                st.success("CSV structure and values passed compatibility checks.")
        bundled_paths = sorted(SAMPLES_DIR.glob("*.csv"))
        selected_path = st.selectbox(
            "Bundled dataset",
            bundled_paths,
            format_func=lambda path: path.name,
            disabled=not bundled_paths,
            help="Used only when no uploaded CSV is selected.",
        )
        instrument = (
            _instrument_from_filename(selected_path)
            if selected_path and uploaded is None
            else ""
        )
        st.subheader("Strategy")
        strategy = st.selectbox(
            "Strategy",
            ["sma", "ema", "rsi"],
            label_visibility="collapsed",
        )
        st.subheader("Capital & Costs")
        initial_cash = st.number_input(
            "Initial capital", min_value=1.0, value=10000.0,
            help="Starting simulated portfolio capital.",
        )
        commission = st.number_input(
            "Commission (%)", min_value=0.0, value=0.1,
            help="Per-execution simulated commission percentage.",
        ) / 100
        slippage = st.number_input(
            "Slippage (%)", min_value=0.0, value=0.05,
            help="Simulated percentage slippage applied by Backtrader.",
        ) / 100
        position_size_pct = st.number_input(
            "Position size (%)",
            min_value=1.0,
            max_value=100.0,
            value=95.0,
            help="Maximum percentage of available cash allocated to a position.",
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
        auto_clean_run = (
            st.button("Clean, organize, and run", type="secondary")
            if uploaded is not None
            and uploaded_cleaning is not None
            and uploaded_cleaning.issues
            and not uploaded_cleaning.data.empty
            else False
        )
    should_run = run or auto_clean_run
    if not should_run:
        st.info("Choose a dataset and configuration, then run the simulation.")
        return
    try:
        if uploaded is not None:
            cleaning = uploaded_cleaning or clean_ohlcv_csv(uploaded.getvalue())
            if cleaning.data.empty:
                raise ValueError("The uploaded CSV has no usable rows or missing required columns.")
            if cleaning.issues and not auto_clean_run:
                st.error(
                    "Compatibility issues were detected. Use "
                    "'Clean, organize, and run' before analysis."
                )
                return
            cleaning_notes = list(cleaning.actions)
            data = validate_ohlcv(cleaning.data, duplicate_policy="raise", cleaning_notes=cleaning_notes)
            metadata = extract_metadata(
                data,
                source=uploaded.name,
                instrument="",
                cleaning_notes=cleaning_notes,
            )
        else:
            data, metadata = load_csv(selected_path, instrument=instrument)
            cleaning_notes = list(metadata.cleaning_notes)
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
    kpi_names = (
        "total_return",
        "sharpe_ratio",
        "max_drawdown",
        "win_rate",
        "profit_factor",
        "completed_trades",
    )
    kpi_labels = (
        "Total Return",
        "Sharpe Ratio",
        "Max Drawdown",
        "Win Rate",
        "Profit Factor",
        "Completed Trades",
    )
    for column, name, label in zip(columns, kpi_names, kpi_labels):
        value = metrics[name]
        if value is None:
            display_value = f"N/A — {notes.get(name, 'undefined')}"
        else:
            display_value = _kpi_value(value, name)
        column.metric(label, display_value, help=f"{label} calculated for this simulation.")
    equity = pd.DataFrame(result.equity_curve) if result.equity_curve else None
    if equity is not None:
        figure = go.Figure(
            go.Scatter(
                x=equity["timestamp"],
                y=equity["value"],
                name="Portfolio Equity",
                line={"color": "#2563eb", "width": 2.5},
                fill="tozeroy",
            )
        )
        figure.add_hline(
            y=result.initial_cash,
            line_dash="dash",
            line_color="#64748b",
            name="Initial Capital",
        )
        figure.update_layout(
            margin={"l": 20, "r": 20, "t": 35, "b": 20},
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="#ffffff",
            legend={"orientation": "h", "y": 1.12},
            hovermode="x unified",
            yaxis={"tickformat": ",.2f", "gridcolor": "#e7edf5"},
            xaxis={"gridcolor": "#eef2f7"},
        )
        st.markdown('<div class="rt-section"></div>', unsafe_allow_html=True)
        st.subheader("Equity Curve")
        st.plotly_chart(figure, use_container_width=True)
    st.subheader("Simulated trade log")
    st.dataframe(result.trades, use_container_width=True)

    report = generate_post_trade_risk_report(
        result,
        metrics,
        cleaning_actions=cleaning_notes,
    )
    st.subheader("Post-Trade & Risk Audit Report")
    st.markdown(report)
    st.download_button(
        "Download audit report (.md)",
        data=report.encode("utf-8"),
        file_name="r_tats_post_trade_risk_audit.md",
        mime="text/markdown",
    )


if __name__ == "__main__":
    main()
