"""Focused tests for uploaded OHLCV compatibility cleaning."""

import pandas as pd
from io import BytesIO, StringIO

from ingestion.cleaner import clean_ohlcv_dataframe, clean_ohlcv_csv


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


def test_cleaner_accepts_file_like_buffers_and_already_numeric_values() -> None:
    csv_text = (
        "Timestamp,Open,High,Low,Close,Volume\n"
        "20240103,10,12,9,11,100\n"
        "20240101,9,11,8,10,90\n"
    )
    from_buffer = clean_ohlcv_csv(StringIO(csv_text))
    from_bytes = clean_ohlcv_csv(csv_text.encode("utf-8"))
    from_binary = clean_ohlcv_csv(BytesIO(csv_text.encode("utf-8")))

    for result in (from_buffer, from_bytes, from_binary):
        assert result.data["Date"].tolist() == ["2024-01-01", "2024-01-03"]
        assert result.data["Open"].tolist() == [9.0, 10.0]
        assert not result.data.isna().any().any()


def test_duplicate_issue_is_not_reported_as_passed_and_cleaning_modifies_data() -> None:
    source = pd.DataFrame({
        "Timestamp": ["2024-01-02", "2024-01-01", "2024-01-02"],
        "Open": [11, 9, 12],
        "High": [13, 11, 14],
        "Low": [10, 8, 11],
        "Close": [12, 10, 13],
        "Volume": [110, 90, 120],
    })

    result = clean_ohlcv_dataframe(source)
    verified = clean_ohlcv_dataframe(result.data)

    assert any("duplicate timestamp" in issue.lower() for issue in result.issues)
    assert any("unsorted" in issue.lower() for issue in result.issues)
    assert len(result.data) == 2
    assert result.data["Date"].tolist() == ["2024-01-01", "2024-01-02"]
    assert not verified.issues
    assert "No compatibility issues were detected." in verified.actions
    assert not verified.modifications


def test_messy_extra_columns_aliases_duplicates_and_formatted_numbers() -> None:
    source = pd.DataFrame({
        " Trade Date ": ["2024-01-03", "2024-01-01", "2024-01-03", "2024-01-02"],
        "Opening": [" $11 ", "$9", "$12", "$10"],
        "High": ["14", "11", "13", "12"],
        "Minimum": ["10", "8", "11", "9"],
        "Adj Close": ["13", "10", "13", "11"],
        "Qty": ["1,000", "900", "1,100", "950"],
        "Symbol": ["ABC", "ABC", "ABC", "ABC"],
    })

    result = clean_ohlcv_dataframe(source)

    assert list(result.data.columns) == ["Date", "Open", "High", "Low", "Close", "Volume"]
    assert result.data["Date"].tolist() == ["2024-01-01", "2024-01-02", "2024-01-03"]
    assert result.data["Volume"].tolist() == [900.0, 950.0, 1100.0]
    assert any("duplicate timestamp" in issue.lower() for issue in result.issues)
    assert any("unsorted" in issue.lower() for issue in result.issues)
    assert result.modifications
    assert result.source_row_count == 4
    assert result.usable_row_count == 3
