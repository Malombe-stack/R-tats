"""TC-07, TC-16, and TC-19 strategy tests."""

from backtesting.runner import run_backtest


def test_tc07_sma_runs(valid_data) -> None:
    result = run_backtest(
        valid_data,
        "sma",
        strategy_params={"fast_period": 3, "slow_period": 5},
    )
    assert result.strategy == "sma"


def test_tc16_all_strategies_run(valid_data) -> None:
    strategies = {
        run_backtest(valid_data, name).strategy for name in ("sma", "ema", "rsi")
    }
    assert strategies == {"sma", "ema", "rsi"}


def test_tc19_unknown_strategy_rejected(valid_data) -> None:
    try:
        run_backtest(valid_data, "unknown")
    except ValueError:
        return
    raise AssertionError("Unknown strategies must be rejected.")
