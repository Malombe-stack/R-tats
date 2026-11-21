"""Validation and metadata extraction for historical OHLCV data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pandas as pd

REQUIRED_COLUMNS: Final[tuple[str, ...]] = (
    "Date", "Open", "High", "Low", "Close", "Volume"
)
_COLUMN_ALIASES: Final[dict[str, str]] = {
    "date": "Date", "timestamp": "Date", "datetime": "Date",
    "open": "Open", "high": "High", "low": "Low",
    "close": "Close", "volume": "Volume",
}


class ValidationError(ValueError):
    """Raised when an OHLCV dataset is invalid."""


@dataclass(frozen=True)
class DatasetMetadata:
    """Describes a validated historical dataset."""

    source: str = ""
    instrument: str = ""
    frequency: str = "Daily"
    start_date: str = ""
    end_date: str = ""
    row_count: int = 0
    cleaning_notes: tuple[str, ...] = ()
    columns: tuple[str, ...] = REQUIRED_COLUMNS

    @property
    def rows(self) -> int:
        """Backward-compatible row count alias."""
        return self.row_count


def validate_ohlcv(
    data: pd.DataFrame,
    duplicate_policy: str = "raise",
    *,
    cleaning_notes: list[str] | None = None,
) -> pd.DataFrame:
    """Normalize and validate an OHLCV frame without mutating its input.

    Args:
        data: Input frame with case-insensitive OHLCV column names.
        duplicate_policy: ``raise`` or explicitly requested ``drop_first``.
        cleaning_notes: Optional list populated with normalization notes.
    """
    if data.empty:
        raise ValidationError("Dataset is empty or contains no usable records.")
    if duplicate_policy not in {"raise", "drop_first"}:
        raise ValueError("duplicate_policy must be 'raise' or 'drop_first'.")
    notes = cleaning_notes if cleaning_notes is not None else []
    result = data.copy()
    renamed: dict[str, str] = {}
    for column in result.columns:
        key = str(column).strip().lower()
        if key in _COLUMN_ALIASES:
            renamed[column] = _COLUMN_ALIASES[key]
    result = result.rename(columns=renamed)
    missing = [column for column in REQUIRED_COLUMNS if column not in result.columns]
    if missing:
        raise ValidationError(f"Missing required columns: {', '.join(missing)}.")
    result = result.loc[:, list(REQUIRED_COLUMNS)]
    parsed_dates = pd.to_datetime(result["Date"], errors="coerce", format="mixed")
    if parsed_dates.isna().any():
        rows = [str(index) for index in result.index[parsed_dates.isna()]]
        raise ValidationError(f"Malformed dates in rows: {', '.join(rows)}.")
    result["Date"] = parsed_dates
    if result["Date"].duplicated().any():
        if duplicate_policy == "raise":
            raise ValidationError("Duplicate timestamps detected.")
        result = result.loc[~result["Date"].duplicated(keep="first")]
        notes.append("Duplicate timestamps dropped using drop_first policy.")
    if not result["Date"].is_monotonic_increasing:
        result = result.sort_values("Date")
        notes.append("Rows sorted chronologically.")
    numeric = ["Open", "High", "Low", "Close", "Volume"]
    for column in numeric:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    if result[numeric].isna().any().any():
        raise ValidationError("OHLCV fields must be numeric and non-missing.")
    prices = ["Open", "High", "Low", "Close"]
    if (result[prices] < 0).any().any():
        raise ValidationError("OHLC prices must be non-negative.")
    if (result["Volume"] < 0).any():
        raise ValidationError("Volume must be non-negative.")
    if (result["High"] < result[["Open", "Close", "Low"]].max(axis=1)).any():
        raise ValidationError("High must be at least Open, Close, and Low.")
    if (result["Low"] > result[["Open", "Close", "High"]].min(axis=1)).any():
        raise ValidationError("Low must be at most Open, Close, and High.")
    if result.empty:
        raise ValidationError("Dataset is empty or contains no usable records.")
    result["Date"] = result["Date"].dt.strftime("%Y-%m-%d")
    return result.reset_index(drop=True)


def extract_metadata(
    data: pd.DataFrame,
    *,
    source: str = "",
    instrument: str = "",
    frequency: str = "Daily",
    cleaning_notes: list[str] | None = None,
) -> DatasetMetadata:
    """Return metadata for a validated dataframe."""
    validated = validate_ohlcv(data, cleaning_notes=cleaning_notes)
    return DatasetMetadata(
        source=source,
        instrument=instrument,
        frequency=frequency,
        start_date=str(validated["Date"].iloc[0]),
        end_date=str(validated["Date"].iloc[-1]),
        row_count=len(validated),
        cleaning_notes=tuple(cleaning_notes or ()),
        columns=tuple(validated.columns),
    )
