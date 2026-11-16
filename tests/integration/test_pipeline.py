"""TC-08, TC-13, TC-14, TC-17, and TC-18 integration tests."""

from analytics.metrics import calculate_metrics
from backtesting.runner import run_backtest
from storage.database import RunRepository


def test_tc08_pipeline(valid_data) -> None:
    result = run_backtest(valid_data, "ema")
    assert result.final_value > 0


def test_tc13_metrics_pipeline(valid_data) -> None:
    result = run_backtest(valid_data, "sma")
    metrics = calculate_metrics(
        result.initial_cash,
        result.final_value,
        result.equity_curve,
        result.trades,
    )
    assert "max_drawdown" in metrics


def test_tc14_sqlite_persistence(valid_data, tmp_path) -> None:
    result = run_backtest(valid_data)
    repo = RunRepository(tmp_path / "runs.sqlite")
    run_id = repo.save_run(result, {"total_return": 0.0})
    assert isinstance(run_id, str)
    assert len(run_id) == 36
    repo.close()


def test_tc17_custom_costs(valid_data) -> None:
    result = run_backtest(valid_data, commission=0.01, slippage=0.001)
    assert result.final_value > 0


def test_tc18_short_dataset_rejected() -> None:
    import pandas as pd
    from ingestion.validator import ValidationError
    with __import__("pytest").raises(ValidationError):
        from ingestion.validator import validate_ohlcv
        columns = ["Date", "Open", "High", "Low", "Close", "Volume"]
        validate_ohlcv(pd.DataFrame(columns=columns))
