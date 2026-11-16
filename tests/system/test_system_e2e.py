"""TC-10 repeatability, TC-11 reporting, and TC-15 scope safety."""

from backtesting.runner import run_backtest
from storage.exporter import DISCLAIMER, export_rows


def test_tc10_repeatability(valid_data) -> None:
    first = run_backtest(valid_data, "sma")
    second = run_backtest(valid_data, "sma")
    assert first == second


def test_tc11_reporting(tmp_path) -> None:
    path = export_rows(tmp_path / "report.csv", [{"value": 1}], ["value"])
    assert DISCLAIMER in path.read_text(encoding="utf-8")


def test_tc15_scope_safety() -> None:
    assert "Simulation only" in DISCLAIMER
    assert "broker" not in DISCLAIMER.lower()
