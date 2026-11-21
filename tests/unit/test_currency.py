"""Unit tests for NSE and US market currency resolution."""

from app.currency import format_currency, resolve_market_currency
from backtesting.runner import BacktestResult
from analytics.post_trade_report import generate_post_trade_risk_report


def test_nse_names_and_tickers_resolve_to_kes() -> None:
    assert resolve_market_currency("NSE_SAMPLE_DAILY.csv") == ("KES", "KSh")
    assert resolve_market_currency("SAFARICOM.NR") == ("KES", "KSh")
    assert resolve_market_currency("Safaricom", ".NR") == ("KES", "KSh")
    assert format_currency(125000.5, "KSh") == "KSh 125,000.50"


def test_spy_and_unrelated_markets_resolve_to_usd() -> None:
    assert resolve_market_currency("SPY_10Y_DAILY.csv") == ("USD", "$")
    assert resolve_market_currency("AAPL.csv") == ("USD", "$")
    assert format_currency(125000.5, "$") == "$125,000.50"


def test_audit_report_uses_nse_kes_labels() -> None:
    result = BacktestResult(
        strategy="sma",
        initial_cash=10000.0,
        final_value=10150.0,
        equity_curve=({"timestamp": "2024-01-01", "value": 10150.0},),
        orders=(),
        trades=(
            {
                "entry_time": "2024-01-01",
                "exit_time": "2024-01-02",
                "quantity": 20,
                "entry_price": 100.0,
                "exit_price": 107.5,
                "commission": 10.0,
                "pnl_net": 140.0,
                "status": "Closed",
                "bar_length": 1,
            },
        ),
    )
    report = generate_post_trade_risk_report(
        result,
        {"max_drawdown": 0.0},
        currency_code="KES",
        currency_symbol="KSh",
    )

    assert "KSh 10,000.00 (KES)" in report
    assert "KSh 100.0000 (KES)" in report
    assert "$" not in report
    assert "dollar" not in report.lower()


def test_audit_report_keeps_usd_for_spy() -> None:
    result = BacktestResult(
        strategy="sma",
        initial_cash=10000.0,
        final_value=10050.0,
        equity_curve=({"timestamp": "2024-01-01", "value": 10050.0},),
        orders=(),
        trades=(),
    )
    report = generate_post_trade_risk_report(
        result,
        {"max_drawdown": 0.0},
        currency_code="USD",
        currency_symbol="$",
    )

    assert "$10,000.00 (USD)" in report
    assert "KSh" not in report
