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
from app.help_text import tooltip
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
[data-testid="stAppViewContainer"] {background: #13101D;}
[data-testid="stHeader"] {background: rgba(19,16,29,0.92);}
[data-testid="stSidebar"] {
    background: #1C172B;
    border-right: 1px solid #2E2644;
}
[data-testid="stMetric"] {
    background: #1C172B;
    border: 1px solid #2E2644;
    border-radius: 12px;
    padding: 14px 16px;
    box-shadow: 0 6px 18px rgba(8, 6, 18, 0.28);
}
[data-testid="stMetricLabel"], [data-testid="stMetricValue"] {
    font-variant-numeric: tabular-nums;
    white-space: normal;
}
[data-testid="stMetricLabel"] {color: #C4B5FD;}
[data-testid="stMetricValue"] {
    color: #F5F3FF;
    font-size: 1.45rem;
    overflow-wrap: anywhere;
}
.rt-header {border-bottom: 1px solid #2E2644; padding-bottom: 0.75rem; margin-bottom: 0.35rem;}
.rt-header h1 {margin-bottom: 0.15rem;}
.rt-subtitle {color: #C4B5FD; font-size: 1.05rem; margin-bottom: 0.35rem;}
.rt-mode {
    display: inline-block; background: rgba(168,85,247,0.16); color: #C4B5FD;
    border: 1px solid #A855F7; border-radius: 999px;
    padding: 0.18rem 0.55rem; font-size: 0.82rem; font-weight: 700;
}
.rt-section {margin-top: 0.25rem;}
[data-testid="stDataFrame"] {
    border: 1px solid #2E2644;
    border-radius: 10px;
    overflow: hidden;
}
div.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #A855F7, #EC4899);
    border: 0;
    color: #FFFFFF;
}
div.stButton > button:focus {
    border-color: #EC4899;
    box-shadow: 0 0 0 2px rgba(236,72,153,0.28);
}
</style>
"""

THEME_COLORS = {
    "canvas": "#13101D",
    "card": "#1C172B",
    "border": "#2E2644",
    "text": "#F5F3FF",
    "secondary": "#C4B5FD",
    "violet": "#A855F7",
    "rose": "#EC4899",
    "positive": "#34D399",
    "loss": "#FB7185",
    "warning": "#FBBF24",
}


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


def _styled_trade_log(trades: tuple[dict[str, Any], ...]) -> Any:
    frame = pd.DataFrame(trades)
    if frame.empty or "pnl_net" not in frame.columns:
        return frame

    def _pnl_color(value: Any) -> str:
        try:
            if float(value) > 0:
                return f"color: {THEME_COLORS['positive']}; font-weight: 700"
            if float(value) < 0:
                return f"color: {THEME_COLORS['loss']}; font-weight: 700"
        except (TypeError, ValueError):
            pass
        return f"color: {THEME_COLORS['secondary']}"

    return frame.style.map(_pnl_color, subset=["pnl_net"])


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
        uploaded = st.file_uploader(
            "Upload OHLCV CSV",
            type="csv",
            help=tooltip("upload"),
        )
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
            help=tooltip("dataset"),
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
            help=tooltip("strategy"),
        )
        st.subheader("Capital & Costs")
        initial_cash = st.number_input(
            "Initial capital",
            min_value=1.0,
            max_value=1e12,
            value=10000.0,
            help=tooltip("initial_capital"),
        )
        commission_percent = st.number_input(
            "Commission (%)",
            min_value=0.0,
            max_value=1000.0,
            value=0.1,
            step=1.0,
            help=tooltip("commission"),
        )
        commission = commission_percent / 100
        slippage_percent = st.number_input(
            "Slippage (%)",
            min_value=0.0,
            max_value=100.0,
            value=0.05,
            step=1.0,
            help=tooltip("slippage"),
        )
        slippage = slippage_percent / 100
        if commission_percent >= 20.0 or slippage_percent >= 20.0:
            st.warning(
                "High-cost stress test active: heavy commission/slippage may erode PnL and returns."
            )
        position_size_pct = st.number_input(
            "Position size (%)",
            min_value=1.0,
            max_value=100.0,
            value=95.0,
            help=tooltip("position_size"),
        ) / 100
        if strategy in {"sma", "ema"}:
            fast = st.number_input(
                "Fast period", min_value=1, value=10, help=tooltip("fast_period"),
            )
            slow = st.number_input(
                "Slow period", min_value=2, value=30, help=tooltip("slow_period"),
            )
            st.caption(f"? SMA: {tooltip('sma')}")
            st.caption(f"EMA: {tooltip('ema')}")
            parameters = {"fast_period": fast, "slow_period": slow}
        else:
            period = st.number_input(
                "RSI period", min_value=2, value=14, help=tooltip("rsi_period"),
            )
            oversold = st.number_input(
                "Oversold", min_value=0.1, max_value=49.9, value=30.0,
                help=tooltip("oversold"),
            )
            overbought = st.number_input(
                "Overbought", min_value=50.1, max_value=99.9, value=70.0,
                help=tooltip("overbought"),
            )
            st.caption(f"? RSI: {tooltip('rsi')}")
            parameters = {
                "rsi_period": period, "oversold": oversold, "overbought": overbought
            }
        run = st.button(
            "Run Backtest",
            type="primary",
            help="Run the existing deterministic simulation with these labeled parameters.",
        )
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
    kpi_help_names = (
        "total_return",
        "sharpe_ratio",
        "max_drawdown",
        "win_rate",
        "profit_factor",
        "completed_trades",
    )
    for column, name, label, help_name in zip(
        columns, kpi_names, kpi_labels, kpi_help_names
    ):
        value = metrics[name]
        if value is None:
            display_value = f"N/A — {notes.get(name, 'undefined')}"
        else:
            display_value = _kpi_value(value, name)
        column.metric(label, display_value, help=tooltip(help_name))
    equity = pd.DataFrame(result.equity_curve) if result.equity_curve else None
    if equity is not None:
        figure = go.Figure(
            go.Scatter(
                x=equity["timestamp"],
                y=equity["value"],
                name="Portfolio Equity",
                line={"color": THEME_COLORS["positive"], "width": 2.5},
                fill="tozeroy",
                fillcolor="rgba(52,211,153,0.10)",
                hovertemplate="<b>%{x}</b><br>Portfolio equity: %{y:,.2f}<extra></extra>",
            )
        )
        figure.add_hline(
            y=result.initial_cash,
            line_dash="dash",
            line_color=THEME_COLORS["violet"],
            name="Initial Capital",
            annotation_text="Initial Capital",
            annotation_font={"color": THEME_COLORS["secondary"]},
        )
        figure.update_layout(
            margin={"l": 20, "r": 20, "t": 35, "b": 20},
            paper_bgcolor=THEME_COLORS["card"],
            plot_bgcolor=THEME_COLORS["card"],
            font={"color": THEME_COLORS["text"]},
            legend={
                "orientation": "h",
                "y": 1.12,
                "font": {"color": THEME_COLORS["secondary"]},
            },
            hovermode="x unified",
            hoverlabel={
                "bgcolor": THEME_COLORS["canvas"],
                "bordercolor": THEME_COLORS["rose"],
                "font": {"color": THEME_COLORS["text"]},
            },
            yaxis={
                "tickformat": ",.2f",
                "gridcolor": THEME_COLORS["border"],
                "zerolinecolor": THEME_COLORS["violet"],
                "tickfont": {"color": THEME_COLORS["secondary"]},
                "title": {"text": "Portfolio equity (capital units)", "font": {"color": THEME_COLORS["secondary"]}},
            },
            xaxis={
                "gridcolor": THEME_COLORS["border"],
                "tickfont": {"color": THEME_COLORS["secondary"]},
                "title": {"text": "Date", "font": {"color": THEME_COLORS["secondary"]}},
            },
        )
        st.markdown('<div class="rt-section"></div>', unsafe_allow_html=True)
        st.subheader("Equity Curve")
        st.caption(
            f"Equity Curve ? {tooltip('equity_curve')} "
            "The horizontal reference is Initial capital (non-percentage capital units)."
        )
        st.plotly_chart(figure, use_container_width=True)
    st.subheader("Simulated trade log")
    st.caption(
        "Trade log fields are non-percentage values. "
        "entry/exit time is a date; quantity is shares; prices and PnL fields are capital units."
    )
    trade_frame = _styled_trade_log(result.trades)
    st.dataframe(
        trade_frame,
        use_container_width=True,
        column_config={
            "entry_time": st.column_config.TextColumn("entry_time", help=tooltip("entry_time")),
            "exit_time": st.column_config.TextColumn("exit_time", help=tooltip("exit_time")),
            "side": st.column_config.TextColumn("side", help="LONG entry or exit side (non-percentage label)."),
            "quantity": st.column_config.NumberColumn("quantity", help=tooltip("quantity"), format="%.4f"),
            "entry_price": st.column_config.NumberColumn("entry_price", help=tooltip("entry_price"), format="$%.4f"),
            "exit_price": st.column_config.NumberColumn("exit_price", help=tooltip("exit_price"), format="$%.4f"),
            "commission": st.column_config.NumberColumn("commission", help=tooltip("commission_field"), format="$%.4f"),
            "profit_loss": st.column_config.NumberColumn("profit_loss", help=tooltip("pnl"), format="$%.4f"),
            "pnl": st.column_config.NumberColumn("pnl", help=tooltip("pnl"), format="$%.4f"),
            "pnl_net": st.column_config.NumberColumn("pnl_net", help=tooltip("pnl_net"), format="$%.4f"),
            "status": st.column_config.TextColumn("status", help="Trade lifecycle status (non-percentage label)."),
            "bar_length": st.column_config.NumberColumn("bar_length", help=tooltip("bar_length"), format="%d"),
        },
    )

    report = generate_post_trade_risk_report(
        result,
        metrics,
        cleaning_actions=cleaning_notes,
        commission_percent=commission_percent,
        slippage_percent=slippage_percent,
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
