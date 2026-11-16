"""TC-01 through TC-06 ingestion tests."""

import pandas as pd
import pytest

from ingestion.validator import ValidationError, validate_ohlcv


def test_tc01_valid_schema(valid_data: pd.DataFrame) -> None:
    assert len(valid_data) >= 500


def test_tc02_missing_column(valid_data: pd.DataFrame) -> None:
    with pytest.raises(ValidationError):
        validate_ohlcv(valid_data.drop(columns=["Volume"]))


def test_tc03_invalid_date(valid_data: pd.DataFrame) -> None:
    invalid = valid_data.copy()
    invalid.loc[0, "Date"] = "bad"
    with pytest.raises(ValidationError):
        validate_ohlcv(invalid)


def test_tc04_duplicate_date(valid_data: pd.DataFrame) -> None:
    invalid = valid_data.copy()
    invalid.loc[1, "Date"] = invalid.loc[0, "Date"]
    with pytest.raises(ValidationError):
        validate_ohlcv(invalid)


def test_tc05_unordered_date(valid_data: pd.DataFrame) -> None:
    invalid = valid_data.iloc[::-1].reset_index(drop=True)
    normalized = validate_ohlcv(invalid)
    assert normalized["Date"].is_monotonic_increasing


def test_tc06_missing_numeric(valid_data: pd.DataFrame) -> None:
    invalid = valid_data.copy()
    invalid.loc[0, "Close"] = None
    with pytest.raises(ValidationError):
        validate_ohlcv(invalid)
