"""Tests for stress-cost execution and percentage/non-percentage help metadata."""

import math
import ast
from pathlib import Path

from app.help_text import HELP, tooltip
from app.main import THEME_COLORS, build_equity_figure
from backtesting.runner import run_backtest
from analytics.metrics import calculate_metrics


def test_extreme_20_percent_commission_and_slippage_are_finite(valid_data) -> None:
    result = run_backtest(
        valid_data,
        "sma",
        initial_cash=10000.0,
        commission=0.20,
        slippage=1.00,
        position_size_pct=0.95,
    )
    metrics = calculate_metrics(
        result.initial_cash,
        result.final_value,
        result.equity_curve,
        result.trades,
    )

    assert math.isfinite(result.final_value)
    assert all(math.isfinite(float(row["value"])) for row in result.equity_curve)
    assert all(
        math.isfinite(float(value))
        for key, value in metrics.items()
        if key != "calculation_notes" and value is not None
    )


def test_percentage_and_non_percentage_definitions_are_explicit() -> None:
    assert "%)" not in HELP["initial_capital"]
    assert "(non-percentage" in HELP["initial_capital"]
    assert "(percentage)" in HELP["commission"]
    assert "Total Return (%)" in tooltip("total_return")
    assert "Sharpe Ratio (non-percentage risk-adjusted ratio)" in tooltip("sharpe_ratio")
    assert "Max Drawdown (%)" in tooltip("max_drawdown")
    assert "Win Rate (%)" in tooltip("win_rate")
    assert "Completed Trades (non-percentage integer count)" in tooltip("completed_trades")
    assert "shares or units bought or traded" in tooltip("quantity")
    assert "does not execute SHORT trades" in tooltip("long_only")


def test_midnight_plum_theme_semantic_colors_are_configured() -> None:
    assert THEME_COLORS["canvas"] == "#13101D"
    assert THEME_COLORS["card"] == "#1C172B"
    assert THEME_COLORS["border"] == "#2E2644"
    assert THEME_COLORS["violet"] == "#A855F7"
    assert THEME_COLORS["rose"] == "#EC4899"
    assert THEME_COLORS["positive"] == "#34D399"
    assert THEME_COLORS["loss"] in {"#FB7185", "#FBBF24"}

    config = (
        Path(__file__).parents[2] / ".streamlit" / "config.toml"
    ).read_text(encoding="utf-8")
    assert 'primaryColor = "#A855F7"' in config
    assert 'backgroundColor = "#13101D"' in config
    assert 'secondaryBackgroundColor = "#1C172B"' in config


def test_long_only_and_unknown_tooltips_are_safe() -> None:
    long_only = tooltip("long_only")
    assert "long-only" in long_only.lower()
    assert "quantity" in long_only.lower()
    assert "shares or units" in long_only.lower()
    assert "not a percentage" in long_only.lower()

    fallback = tooltip("unregistered_future_term")
    assert "Unregistered Future Term" in fallback
    assert "additional information is not currently available" in fallback


def test_all_literal_app_tooltip_keys_exist() -> None:
    app_dir = Path(__file__).parents[2] / "app"
    missing: set[str] = set()
    for source_path in app_dir.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            if not isinstance(function, ast.Name) or function.id != "tooltip":
                continue
            if not node.args:
                continue
            argument = node.args[0]
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                if argument.value not in HELP:
                    missing.add(argument.value)

    assert not missing


def test_equity_chart_guards_none_nan_and_extreme_values() -> None:
    figure = build_equity_figure(
        [
            {"timestamp": "2024-01-01", "value": 100.0},
            {"timestamp": "2024-01-02", "value": float("nan")},
            {"timestamp": "2024-01-03", "value": float("inf")},
            {"timestamp": "2024-01-04", "value": 120.0},
        ],
        float("nan"),
        "KES",
        "KSh",
    )

    assert isinstance(figure.layout.legend.y, (int, float))
    assert figure.layout.legend.y == 1.12
    assert figure.layout.legend.orientation == "h"
    assert len(figure.data) == 1
    assert all(math.isfinite(float(value)) for value in figure.data[0].y)
