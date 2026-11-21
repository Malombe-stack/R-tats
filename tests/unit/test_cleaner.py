"""Focused tests for uploaded OHLCV compatibility cleaning."""

import pandas as pd

from ingestion.cleaner import clean_ohlcv_dataframe


def test_cleaner_normalizes_aliases_sanitizes_values_and_sorts_dates() -> None:
    source = pd.DataFrame({
        " Timestamp ": ["2024-01-03", "2024-01-01", "2024-01-02"],
        "Open Price": [" $10 ", "$9", "$11"],
        "High": ["12", "11", "13"],
        "Low": ["9", "8", "10"],
        "Close": ["11", "10", "12"],
        "Vol": ["1,000", "900", "950"],
    })

    result = clean_ohlcv_dataframe(source)

    assert result.data["Date"].tolist() == ["2024-01-01", "2024-01-02", "2024-01-03"]
    assert result.data["Open"].tolist() == [9.0, 11.0, 10.0]
    assert result.data["Volume"].tolist() == [900.0, 950.0, 1000.0]
    assert any("Sorted rows chronologically" in action for action in result.actions)


def test_cleaner_drops_duplicate_missing_and_invalid_rows() -> None:
    source = pd.DataFrame({
        "Date": ["2024-01-01", "2024-01-01", "bad-date", "2024-01-04"],
        "Open": ["10", "11", "12", "-1"],
        "High": ["12", "13", "14", "1"],
        "Low": ["9", "10", "11", "-2"],
        "Close": ["11", "12", "13", "0"],
        "Volume": ["100", "110", "120", "130"],
    })

    result = clean_ohlcv_dataframe(source)

    assert result.data["Date"].tolist() == ["2024-01-01"]
    assert result.data["Close"].tolist() == [12.0]
    assert any("duplicate timestamp" in issue.lower() for issue in result.issues)
    assert any("Dropped" in action for action in result.actions)


def test_cleaner_reports_missing_required_columns() -> None:
    result = clean_ohlcv_dataframe(pd.DataFrame({"Date": ["2024-01-01"], "Close": [10]}))

    assert result.data.empty
    assert any("Missing required columns" in issue for issue in result.issues)
