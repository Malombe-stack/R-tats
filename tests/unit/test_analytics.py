"""TC-09 and TC-12 analytics tests."""

from analytics.metrics import calculate_metrics


def test_tc09_metrics() -> None:
    metrics = calculate_metrics(
        100.0,
        110.0,
        [{"value": 100.0}, {"value": 105.0}, {"value": 110.0}],
        [{"pnl_net": 10.0}, {"pnl_net": -2.0}],
    )
    assert metrics["total_return"] == 10.0
    assert metrics["win_rate"] == 50.0
    assert metrics["profit_factor"] == 5.0


def test_tc12_empty_trades() -> None:
    metrics = calculate_metrics(100.0, 100.0, [{"value": 100.0}], [])
    assert metrics["trade_count"] == 0
    assert metrics["win_rate"] is None
    assert metrics["calculation_notes"]["win_rate"] == "Undefined: 0 completed trades"


def test_finite_guards_filter_nan_and_infinite_values() -> None:
    metrics = calculate_metrics(
        100.0,
        float("inf"),
        [
            {"value": 100.0},
            {"value": float("nan")},
            {"value": 90.0},
            {"value": float("inf")},
        ],
        [{"pnl_net": float("nan")}, {"pnl_net": 5.0}, {"pnl_net": -2.0}],
    )
    assert metrics["total_return"] == 0.0
    assert metrics["win_rate"] == 50.0
    assert metrics["profit_factor"] == 2.5
