"""Focused tests for the post-trade and risk audit report."""

from analytics.post_trade_report import generate_post_trade_risk_report
from analytics.report_exports import report_to_pdf, report_to_txt
from backtesting.runner import BacktestResult


def test_report_summarizes_winning_and_losing_trades() -> None:
    result = BacktestResult(
        strategy="sma",
        initial_cash=10000.0,
        final_value=10100.0,
        equity_curve=(
            {"timestamp": "2024-01-01", "value": 10000.0},
            {"timestamp": "2024-01-02", "value": 10000.0},
            {"timestamp": "2024-01-03", "value": 10000.0},
            {"timestamp": "2024-01-04", "value": 10100.0},
        ),
        orders=(
            {"date": "2024-01-02", "status": "Risk Rejected", "reason": "Insufficient capital"},
        ),
        trades=(
            {
                "entry_time": "2024-01-01", "exit_time": "2024-01-03",
                "quantity": 10, "entry_price": 100.0, "exit_price": 112.0,
                "commission": 2.0, "pnl_net": 118.0, "pnl": 120.0,
                "status": "Closed", "bar_length": 2,
            },
            {
                "entry_time": "2024-01-03", "exit_time": "2024-01-04",
                "quantity": 10, "entry_price": 112.0, "exit_price": 110.0,
                "commission": 2.0, "pnl_net": -22.0, "pnl": -20.0,
                "status": "Closed", "bar_length": 1,
            },
        ),
    )
    metrics = {"max_drawdown": 1.25}

    report = generate_post_trade_risk_report(
        result,
        metrics,
        cleaning_actions=("Sorted rows chronologically.", "Dropped 1 invalid OHLCV row."),
    )

    assert "What Worked" in report
    assert "Strongest trade" in report
    assert "Average holding period" in report
    assert "Losing trades: **1**" in report
    assert "1.25%" in report
    assert "2024-01-02" in report
    assert "Insufficient capital" in report
    assert "Dropped 1 invalid OHLCV row." in report


def test_report_states_no_risk_rejections() -> None:
    result = BacktestResult(
        strategy="rsi",
        initial_cash=5000.0,
        final_value=5000.0,
        equity_curve=(),
        orders=({"date": "2024-01-01", "status": "Completed", "side": "BUY"},),
        trades=(),
    )

    report = generate_post_trade_risk_report(result, {"max_drawdown": 0.0})

    assert "`0 orders blocked by risk checks`" in report
    assert "No executed trades" in report
    assert "no auto-cleaning actions" in report


def test_report_flags_high_commission_stress() -> None:
    result = BacktestResult(
        strategy="sma",
        initial_cash=10000.0,
        final_value=8000.0,
        equity_curve=(
            {"timestamp": "2024-01-01", "value": 10000.0},
            {"timestamp": "2024-01-02", "value": 8000.0},
        ),
        orders=(),
        trades=(),
    )

    report = generate_post_trade_risk_report(
        result,
        {"max_drawdown": 20.0},
        commission_percent=20.0,
        slippage_percent=100.0,
    )

    assert "Commission: **20.00%**" in report
    assert "Slippage: **100.00%**" in report
    assert "High-Cost Stress Test" in report


def test_plain_text_report_export_is_readable_and_not_markdown() -> None:
    markdown_report = """# Post-Trade & Risk Audit Report

## What Worked

- Total net PnL after commission: **120.00**.

| Side | Quantity | Net PnL |
|---|---:|---:|
| LONG entry / closed exit | 10.0000 | 118.0000 |
"""

    text_report = report_to_txt(markdown_report)

    assert "Post-Trade & Risk Audit Report" in text_report
    assert "What Worked" in text_report
    assert "Total net PnL after commission: 120.00." in text_report
    assert "LONG entry / closed exit | 10.0000 | 118.0000" in text_report
    assert "**" not in text_report
    assert "|---|" not in text_report


def test_pdf_report_export_returns_a_pdf_document() -> None:
    markdown_report = """# Post-Trade & Risk Audit Report

## What Worked

- 1 profitable trade.

## Risk Check Rejections & Data Hygiene

- `0 orders blocked by risk checks`
"""

    pdf_report = report_to_pdf(markdown_report)

    assert pdf_report.startswith(b"%PDF-")
    assert len(pdf_report) > 500
