"""Streamlit dashboard for the R-TATS academic simulation."""

from __future__ import annotations

import re
import sys
import hashlib
import math
from pathlib import Path
from collections.abc import Iterable
from typing import Any

import plotly.graph_objects as go
import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analytics.metrics import calculate_metrics
from analytics.post_trade_report import generate_post_trade_risk_report
from analytics.report_exports import report_to_pdf, report_to_txt
from app.currency import resolve_market_currency
from app.help_text import tooltip
from backtesting.runner import run_backtest
from ingestion.cleaner import (
    CleaningResult,
    clean_ohlcv_csv,
    clean_ohlcv_dataframe,
    normalize_cleaning_result,
)
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
    try:
        if name in {"total_return", "max_drawdown", "win_rate"}:
            number = float(value)
            return f"{number:.2f}%" if math.isfinite(number) else "N/A"
        if name in {"sharpe_ratio", "profit_factor"}:
            number = float(value)
            return f"{number:.2f}" if math.isfinite(number) else "N/A"
        return f"{int(float(value)):,}" if math.isfinite(float(value)) else "N/A"
    except (TypeError, ValueError, OverflowError):
        return "N/A"


def _cleaned_csv_bytes(cleaned: pd.DataFrame) -> bytes:
    return cleaned.to_csv(index=False).encode("utf-8")


def _safe_cleaning_count(value: Any) -> int:
    """Convert cleaning row counts to a non-negative integer."""
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, number)


def normalize_cleaning_notes(value: Any) -> list[str]:
    """Normalize cleaning notes to a mutable list of display-safe strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [str(value)]
    if isinstance(value, Iterable):
        return [str(note) for note in value if note is not None]
    return [str(value)]


@st.cache_data(show_spinner=False)
def _clean_uploaded_bytes(payload: bytes) -> CleaningResult:
    """Cache deterministic cleaning of unchanged uploaded bytes."""
    return clean_ohlcv_csv(payload)


@st.cache_data(show_spinner=False)
def _load_bundled_cached(path_text: str, instrument: str) -> tuple[pd.DataFrame, Any]:
    return load_csv(Path(path_text), instrument=instrument)


@st.cache_data(show_spinner=False)
def _run_backtest_cached(
    data: pd.DataFrame,
    strategy: str,
    initial_cash: float,
    commission: float,
    slippage: float,
    parameters_json: tuple[tuple[str, Any], ...],
    position_size_pct: float,
) -> Any:
    parameters = dict(parameters_json)
    return run_backtest(
        data,
        strategy,
        initial_cash,
        commission,
        slippage,
        parameters,
        position_size_pct=position_size_pct,
    )


@st.cache_data(show_spinner=False)
def _calculate_metrics_cached(
    initial_cash: float,
    final_value: float,
    equity_curve: tuple[dict[str, Any], ...],
    trades: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    return calculate_metrics(initial_cash, final_value, equity_curve, trades)


def _styled_trade_log(trades: Any) -> Any:
    if isinstance(trades, dict):
        trade_rows = [trades]
    elif isinstance(trades, Iterable) and not isinstance(trades, (str, bytes)):
        trade_rows = [trade for trade in trades if isinstance(trade, dict)]
    else:
        trade_rows = []
    frame = pd.DataFrame(trade_rows)
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


def _finite_chart_number(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if math.isfinite(number) else fallback


def build_equity_figure(
    equity_curve: Any,
    initial_cash: Any,
    currency_code: Any,
    currency_symbol: Any,
) -> go.Figure:
    """Build a Plotly chart from finite, typed chart inputs."""
    code = str(currency_code or "USD")
    symbol = str(currency_symbol or "$")
    baseline = _finite_chart_number(initial_cash, 0.0)

    if isinstance(equity_curve, dict):
        equity_rows = [equity_curve]
    elif isinstance(equity_curve, Iterable) and not isinstance(equity_curve, (str, bytes)):
        equity_rows = [row for row in equity_curve if isinstance(row, dict)]
    else:
        equity_rows = []
    frame = pd.DataFrame(equity_rows)
    if not frame.empty:
        if "timestamp" not in frame.columns:
            frame["timestamp"] = frame.get("date", "")
        if "value" not in frame.columns:
            frame["value"] = frame.get("portfolio_value", baseline)
        frame["timestamp"] = frame["timestamp"].astype(str)
        frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
        frame = frame.replace([float("inf"), float("-inf")], float("nan")).dropna(
            subset=["value", "timestamp"]
        )
    if frame.empty:
        frame = pd.DataFrame({"timestamp": [], "value": []})

    figure = go.Figure(
        go.Scatter(
            x=frame["timestamp"].tolist(),
            y=[_finite_chart_number(value, baseline) for value in frame["value"].tolist()],
            name="Portfolio Equity",
            line={"color": THEME_COLORS["positive"], "width": 2.5},
            fill="tozeroy",
            fillcolor="rgba(52,211,153,0.10)",
            hovertemplate=(
                "<b>%{x}</b><br>Portfolio equity: "
                + (symbol if symbol == "$" else "KSh ")
                + "%{y:,.2f}<extra></extra>"
            ),
        )
    )
    if math.isfinite(baseline):
        figure.add_hline(
            y=baseline,
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
            "y": float(1.12),
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
            "tickprefix": "$" if symbol == "$" else "KSh ",
            "gridcolor": THEME_COLORS["border"],
            "zerolinecolor": THEME_COLORS["violet"],
            "tickfont": {"color": THEME_COLORS["secondary"]},
            "title": {
                "text": f"Portfolio equity ({code} capital units)",
                "font": {"color": THEME_COLORS["secondary"]},
            },
        },
        xaxis={
            "gridcolor": THEME_COLORS["border"],
            "tickfont": {"color": THEME_COLORS["secondary"]},
            "title": {"text": "Date", "font": {"color": THEME_COLORS["secondary"]}},
        },
    )
    return figure


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
            uploaded_bytes = uploaded.getvalue()
            upload_key = hashlib.sha256(uploaded_bytes).hexdigest()
            cache_key = f"{uploaded.name}:{len(uploaded_bytes)}:{upload_key}"
            cached_key = st.session_state.get("uploaded_csv_cache_key")
            if cached_key != cache_key:
                try:
                    uploaded_cleaning = normalize_cleaning_result(
                        _clean_uploaded_bytes(uploaded_bytes)
                    )
                except (OSError, ValueError) as error:
                    from ingestion.cleaner import CleaningResult
                    uploaded_cleaning = CleaningResult(
                        pd.DataFrame(columns=("Date", "Open", "High", "Low", "Close", "Volume")),
                        (str(error),),
                        (f"CSV parsing failed: {error}",),
                    )
                st.session_state["uploaded_csv_cache_key"] = cache_key
                st.session_state["uploaded_csv_bytes"] = uploaded_bytes
                st.session_state["uploaded_csv_name"] = uploaded.name
                st.session_state["uploaded_cleaning"] = uploaded_cleaning
            else:
                uploaded_cleaning = normalize_cleaning_result(
                    st.session_state.get("uploaded_cleaning")
                )
            if uploaded_cleaning.data.empty:
                st.error("Issues detected")
                for issue in uploaded_cleaning.issues:
                    st.write(f"- {issue}")
                st.warning("Required columns are missing or no usable rows remain.")
            else:
                post_clean_check = clean_ohlcv_dataframe(uploaded_cleaning.data)
                st.session_state["uploaded_post_clean_check"] = post_clean_check
                modifications = uploaded_cleaning.modifications
                if modifications:
                    st.success(
                        f"Auto-cleaned & ready: {uploaded_cleaning.source_row_count} source row(s) "
                        f"extracted; {len(uploaded_cleaning.data)} usable row(s); "
                        f"{len(modifications)} cleaning action(s) applied."
                    )
                    st.caption("Cleaning summary")
                    for action in modifications:
                        st.write(f"- {action}")
                else:
                    st.success(
                        f"Clean OHLCV data loaded: {uploaded_cleaning.source_row_count} source "
                        f"row(s) extracted; {len(uploaded_cleaning.data)} usable row(s)."
                    )
                if uploaded_cleaning.issues:
                    st.caption("Original issues detected and resolved")
                    for issue in uploaded_cleaning.issues:
                        st.write(f"- {issue}")
                if post_clean_check.issues:
                    st.warning("Post-clean verification found remaining issues:")
                    for issue in post_clean_check.issues:
                        st.write(f"- {issue}")
                else:
                    st.caption(
                        f"Post-clean verification passed: {len(uploaded_cleaning.data)} usable row(s) remain."
                    )
                st.download_button(
                    "Download cleaned CSV",
                    data=_cleaned_csv_bytes(uploaded_cleaning.data),
                    file_name="r_tats_cleaned.csv",
                    mime="text/csv",
                    key="cleaned_csv_download",
                )
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
    should_run = run
    if not should_run:
        st.info("Choose a dataset and configuration, then run the simulation.")
        return
    try:
        if uploaded is not None:
            cleaning = normalize_cleaning_result(
                uploaded_cleaning or clean_ohlcv_csv(uploaded.getvalue())
            )
            if cleaning.data.empty:
                raise ValueError("The uploaded CSV has no usable rows or missing required columns.")
            post_clean_check = clean_ohlcv_dataframe(cleaning.data)
            cleaning_notes = normalize_cleaning_notes(None)
            if cleaning.issues:
                cleaning_notes.extend(f"Issue detected: {issue}" for issue in cleaning.issues)
            if cleaning.modifications:
                cleaning_notes.extend(
                    f"Cleaning action: {action}" for action in cleaning.modifications
                )
            usable_count = _safe_cleaning_count(cleaning.usable_row_count)
            source_count = _safe_cleaning_count(cleaning.source_row_count)
            cleaning_notes.append(
                f"Extraction/cleaning count: kept {usable_count} usable row(s) "
                f"from {source_count} source row(s); extracted 6 required OHLCV columns."
            )
            if post_clean_check.issues:
                cleaning_notes.extend(
                    f"Post-clean issue remaining: {issue}"
                    for issue in post_clean_check.issues
                )
            else:
                cleaning_notes.append(
                    f"Post-clean verification passed: {_safe_cleaning_count(len(cleaning.data))} usable row(s) remain "
                    "with normalized columns, chronological dates, and valid OHLCV values."
                )
            data = validate_ohlcv(cleaning.data, duplicate_policy="raise", cleaning_notes=cleaning_notes)
            metadata = extract_metadata(
                data,
                source=uploaded.name,
                instrument="",
                cleaning_notes=cleaning_notes,
            )
        else:
            data, metadata = _load_bundled_cached(str(selected_path), instrument)
            cleaning_notes = normalize_cleaning_notes(metadata.cleaning_notes)
        result = _run_backtest_cached(
            data,
            strategy,
            initial_cash,
            commission,
            slippage,
            tuple(sorted(parameters.items())),
            position_size_pct=position_size_pct,
        )
        currency_source = (
            uploaded.name if uploaded is not None
            else str(selected_path)
        )
        currency_code, currency_symbol = resolve_market_currency(
            currency_source,
            instrument,
            metadata.instrument,
        )
        trade_currency_format = (
            "$%.4f" if currency_symbol == "$" else "KSh %.4f"
        )
        metrics = _calculate_metrics_cached(
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
    result_equity = getattr(result, "equity_curve", ()) or ()
    if isinstance(result_equity, dict):
        equity_rows = [result_equity]
    elif isinstance(result_equity, Iterable) and not isinstance(result_equity, (str, bytes)):
        equity_rows = [row for row in result_equity if isinstance(row, dict)]
    else:
        equity_rows = []
    equity = pd.DataFrame(equity_rows) if equity_rows else None
    if equity is not None:
        figure = build_equity_figure(
            equity,
            result.initial_cash,
            currency_code,
            currency_symbol,
        )
        st.markdown('<div class="rt-section"></div>', unsafe_allow_html=True)
        st.subheader("Equity Curve")
        st.caption(
            f"Equity Curve ? {tooltip('equity_curve')} "
            f"The horizontal reference is Initial capital ({currency_code} capital units)."
        )
        st.plotly_chart(figure, use_container_width=True)
    st.subheader("Simulated trade log")
    st.caption(
        "Trade log fields are non-percentage values. "
        "entry/exit time is a date; quantity is shares/units; prices and PnL fields are capital units."
    )
    st.caption(f"? Execution scope: {tooltip('long_only')}")
    trade_frame = _styled_trade_log(result.trades)
    st.dataframe(
        trade_frame,
        use_container_width=True,
        column_config={
            "entry_time": st.column_config.TextColumn("entry_time", help=tooltip("entry_time")),
            "exit_time": st.column_config.TextColumn("exit_time", help=tooltip("exit_time")),
            "side": st.column_config.TextColumn("side", help="LONG entry or exit side (non-percentage label)."),
            "quantity": st.column_config.NumberColumn("quantity", help=tooltip("quantity"), format="%.4f"),
            "entry_price": st.column_config.NumberColumn("entry_price", help=tooltip("entry_price"), format=trade_currency_format),
            "exit_price": st.column_config.NumberColumn("exit_price", help=tooltip("exit_price"), format=trade_currency_format),
            "commission": st.column_config.NumberColumn("commission", help=tooltip("commission_field"), format=trade_currency_format),
            "profit_loss": st.column_config.NumberColumn("profit_loss", help=tooltip("pnl"), format=trade_currency_format),
            "pnl": st.column_config.NumberColumn("pnl", help=tooltip("pnl"), format=trade_currency_format),
            "pnl_net": st.column_config.NumberColumn("pnl_net", help=tooltip("pnl_net"), format=trade_currency_format),
            "status": st.column_config.TextColumn("status", help="Trade lifecycle status (non-percentage label)."),
            "bar_length": st.column_config.NumberColumn("bar_length", help=tooltip("bar_length"), format="%d"),
        },
    )

    report = generate_post_trade_risk_report(
        result,
        metrics if isinstance(metrics, dict) else {},
        cleaning_actions=cleaning_notes,
        commission_percent=commission_percent,
        slippage_percent=slippage_percent,
        currency_code=currency_code,
        currency_symbol=currency_symbol,
    )
    st.subheader("Post-Trade & Risk Audit Report")
    st.markdown(report)
    txt_report = report_to_txt(report)
    pdf_report = report_to_pdf(report)
    txt_column, pdf_column = st.columns(2)
    txt_column.download_button(
        "Download audit report (.txt)",
        data=txt_report.encode("utf-8"),
        file_name="r_tats_post_trade_risk_audit.txt",
        mime="text/plain",
        help="Plain text: portable, readable report with all report sections.",
    )
    pdf_column.download_button(
        "Download audit report (.pdf)",
        data=pdf_report,
        file_name="r_tats_post_trade_risk_audit.pdf",
        mime="application/pdf",
        help="PDF: formatted report for customer review or archiving.",
    )


if __name__ == "__main__":
    main()
