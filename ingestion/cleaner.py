"""User-facing CSV compatibility inspection and deterministic cleaning."""

from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO, StringIO
from pathlib import Path
from typing import BinaryIO

import pandas as pd


REQUIRED_COLUMNS = ("Date", "Open", "High", "Low", "Close", "Volume")


@dataclass(frozen=True)
class CleaningResult:
    """A cleaned frame and an auditable description of every transformation."""

    data: pd.DataFrame
    issues: tuple[str, ...]
    actions: tuple[str, ...]

    @property
    def cleaning_summary(self) -> tuple[str, ...]:
        return self.actions


def _normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())


_ALIASES = {
    "date": "Date", "timestamp": "Date", "datetime": "Date",
    "tradedate": "Date", "open": "Open", "openprice": "Open",
    "high": "High", "highprice": "High", "low": "Low",
    "lowprice": "Low", "close": "Close", "closeprice": "Close",
    "adjclose": "Close", "volume": "Volume", "vol": "Volume",
}


def clean_ohlcv_dataframe(data: pd.DataFrame) -> CleaningResult:
    """Normalize aliases and remove unusable OHLCV rows deterministically."""
    if data.empty:
        return CleaningResult(data=data.copy(), issues=("The CSV is empty.",), actions=())

    frame = data.copy()
    issues: list[str] = []
    actions: list[str] = []
    renamed: dict[str, str] = {}

    for column in frame.columns:
        normalized = _normalized_key(column)
        target = _ALIASES.get(normalized)
        if target is not None:
            renamed[column] = target
    if renamed:
        frame = frame.rename(columns=renamed)

    if len(set(frame.columns) - set(REQUIRED_COLUMNS)) == len(frame.columns):
        issues.append("Required OHLCV column names were not recognized.")
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        issues.append(f"Missing required columns: {', '.join(missing)}.")
        actions.append("Column names were inspected, but missing columns cannot be inferred.")
        empty = pd.DataFrame(columns=REQUIRED_COLUMNS)
        return CleaningResult(empty, tuple(issues), tuple(actions))

    frame = frame.loc[:, REQUIRED_COLUMNS].copy()
    if list(frame.columns) != list(REQUIRED_COLUMNS):
        actions.append("Required OHLCV columns were reordered.")

    original_columns = tuple(str(column).strip().lower() for column in data.columns)
    if any(column not in {"date", "timestamp", "datetime", "open", "high", "low", "close", "volume",
                           "tradedate", "openprice", "highprice", "lowprice", "closeprice",
                           "adjclose", "vol"} for column in original_columns):
        actions.append("Only recognized OHLCV columns were retained.")

    parsed = pd.to_datetime(frame["Date"], errors="coerce", format="mixed")
    malformed_dates = int(parsed.isna().sum())
    if malformed_dates:
        issues.append(f"{malformed_dates} row(s) contain unparsed timestamps.")
    frame["Date"] = parsed

    numeric_columns = ("Open", "High", "Low", "Close", "Volume")
    for column in numeric_columns:
        sanitized = (
            frame[column].astype("string").str.strip()
            .str.replace(r"[$,\s]", "", regex=True)
            .str.replace(r"\((.*)\)", r"-\1", regex=True)
        )
        converted = pd.to_numeric(sanitized, errors="coerce")
        numeric_issues = int(converted.isna().sum())
        if numeric_issues:
            issues.append(f"{numeric_issues} value(s) in {column} could not be parsed.")
        frame[column] = converted

    valid = parsed.notna() & frame[list(numeric_columns)].notna().all(axis=1)
    missing_count = int((~valid).sum())
    if missing_count:
        actions.append(f"Dropped {missing_count} row(s) with missing or unparsed date/numeric fields.")

    frame = frame.loc[valid].copy()
    duplicate_count = int(frame["Date"].duplicated(keep="first").sum())
    if duplicate_count:
        issues.append(f"{duplicate_count} duplicate timestamp(s) detected.")
        frame = frame.sort_values("Date", kind="stable").drop_duplicates("Date", keep="last")
        actions.append(f"Removed {duplicate_count} duplicate timestamp(s), keeping the last record deterministically.")

    frame = frame.sort_values("Date", kind="stable").reset_index(drop=True)
    actions.append("Sorted rows chronologically by timestamp.")

    price_columns = ("Open", "High", "Low", "Close")
    invalid_mask = (
        (frame[list(price_columns)] <= 0).any(axis=1)
        | (frame["High"] < frame["Low"])
        | (frame["High"] < frame[["Open", "Close", "Low"]].max(axis=1))
        | (frame["Low"] > frame[["Open", "Close", "High"]].min(axis=1))
        | (frame["Volume"] < 0)
    )
    invalid_count = int(invalid_mask.sum())
    if invalid_count:
        issues.append(
            f"{invalid_count} invalid OHLCV row(s) found (zero/negative prices, bad high/low, or negative volume)."
        )
        frame = frame.loc[~invalid_mask].copy()
        actions.append(f"Dropped {invalid_count} invalid OHLCV row(s).")

    frame["Date"] = frame["Date"].dt.strftime("%Y-%m-%d")
    if not issues:
        actions.append("No compatibility issues were detected.")
    elif not actions:
        actions.append("The dataset was inspected; no rows required removal.")
    return CleaningResult(frame.reset_index(drop=True), tuple(issues), tuple(actions))


def clean_ohlcv_csv(source: str | Path | bytes | BinaryIO | pd.DataFrame) -> CleaningResult:
    """Read a CSV source and return cleaned OHLCV data and a structured summary."""
    if isinstance(source, pd.DataFrame):
        return clean_ohlcv_dataframe(source)
    if isinstance(source, bytes):
        data = pd.read_csv(BytesIO(source))
    elif isinstance(source, str) or isinstance(source, Path):
        data = pd.read_csv(source)
    else:
        data = pd.read_csv(source)
    return clean_ohlcv_dataframe(data)
