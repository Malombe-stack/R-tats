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
    source_row_count: int = 0
    usable_row_count: int = 0

    @property
    def cleaning_summary(self) -> tuple[str, ...]:
        return self.actions

    @property
    def modifications(self) -> tuple[str, ...]:
        """Only real cleaning/status actions, excluding no-op conclusions."""
        excluded = {
            "No compatibility issues were detected.",
            "The dataset was inspected; no rows required removal.",
        }
        return tuple(
            action for action in self.actions
            if action not in excluded
            and not action.startswith("Extraction/cleaning count:")
        )


def normalize_cleaning_result(value: object) -> CleaningResult:
    """Normalize dataclass, dict, or empty session values into a safe result."""
    if isinstance(value, CleaningResult):
        return value
    if isinstance(value, dict):
        data = value.get("data")
        if not isinstance(data, pd.DataFrame):
            data = pd.DataFrame()
        issues_value = value.get("issues", ())
        actions_value = value.get("actions", value.get("modifications", ()))
        issues = tuple(str(item) for item in issues_value) if isinstance(issues_value, (list, tuple, set)) else ()
        actions = tuple(str(item) for item in actions_value) if isinstance(actions_value, (list, tuple, set)) else ()
        try:
            source_count = int(value.get("source_row_count", len(data)) or 0)
        except (TypeError, ValueError):
            source_count = len(data)
        try:
            usable_count = int(value.get("usable_row_count", len(data)) or 0)
        except (TypeError, ValueError):
            usable_count = len(data)
        return CleaningResult(
            data=data,
            issues=issues,
            actions=actions,
            source_row_count=max(0, source_count),
            usable_row_count=max(0, usable_count),
        )
    return CleaningResult(
        data=pd.DataFrame(columns=REQUIRED_COLUMNS),
        issues=("The uploaded CSV result could not be restored.",),
        actions=("CSV parsing failed safely; re-upload the file.",),
        source_row_count=0,
        usable_row_count=0,
    )


def _normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())


_ALIASES = {
    "date": "Date", "timestamp": "Date", "datetime": "Date",
    "tradedate": "Date", "open": "Open", "openprice": "Open",
    "opening": "Open", "openingprice": "Open",
    "high": "High", "highprice": "High", "low": "Low",
    "lowprice": "Low", "maximum": "High", "minimum": "Low",
    "close": "Close", "closeprice": "Close", "closing": "Close",
    "closingprice": "Close", "adjclose": "Close", "adjustedclose": "Close",
    "volume": "Volume", "vol": "Volume", "qty": "Volume",
    "quantity": "Volume", "tradingvolume": "Volume", "totalvolume": "Volume",
}


def _parse_dates(values: pd.Series) -> pd.Series:
    """Parse string or numeric dates without confusing numeric bars with ns timestamps."""
    raw = values.astype("string").str.strip()
    numeric = pd.to_numeric(raw, errors="coerce")
    numeric_mask = numeric.notna() & raw.notna()
    if numeric_mask.all():
        integer = numeric.dropna()
        if integer.abs().between(10_000_000, 99_999_999).all():
            return pd.to_datetime(raw, format="%Y%m%d", errors="coerce")
        if integer.abs().ge(1_000_000_000).all():
            unit = "ms" if integer.abs().ge(100_000_000_000).all() else "s"
            return pd.to_datetime(numeric, unit=unit, errors="coerce")
    return pd.to_datetime(raw, errors="coerce", format="mixed")


def clean_ohlcv_dataframe(data: pd.DataFrame) -> CleaningResult:
    """Normalize aliases and remove unusable OHLCV rows deterministically."""
    if data.empty:
        return CleaningResult(
            data=data.copy(),
            issues=("The CSV is empty.",),
            actions=(),
            source_row_count=0,
            usable_row_count=0,
        )

    frame = data.copy()
    source_row_count = len(frame)
    issues: list[str] = []
    actions: list[str] = []
    renamed: dict[str, str] = {}
    renamed_count = 0

    for column in frame.columns:
        normalized = _normalized_key(column)
        target = _ALIASES.get(normalized)
        if target is not None:
            renamed[column] = target
            if str(column).strip() != target:
                issues.append(f"Column alias `{column}` was normalized to `{target}`.")
                renamed_count += 1
    if renamed:
        frame = frame.rename(columns=renamed)
        if renamed_count:
            actions.append(f"Normalized {renamed_count} column name/alias(es).")
        if frame.columns.duplicated().any():
            frame = frame.loc[:, ~frame.columns.duplicated(keep="last")]

    if len(set(frame.columns) - set(REQUIRED_COLUMNS)) == len(frame.columns):
        issues.append("Required OHLCV column names were not recognized.")
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        issues.append(f"Missing required columns: {', '.join(missing)}.")
        actions.append("Column names were inspected, but missing columns cannot be inferred.")
        empty = pd.DataFrame(columns=REQUIRED_COLUMNS)
        return CleaningResult(
            empty,
            tuple(issues),
            tuple(actions),
            source_row_count=source_row_count,
            usable_row_count=0,
        )

    frame = frame.loc[:, REQUIRED_COLUMNS].copy()
    if list(frame.columns) != list(REQUIRED_COLUMNS):
        actions.append("Required OHLCV columns were reordered.")

    original_columns = tuple(str(column).strip().lower() for column in data.columns)
    if any(column not in {"date", "timestamp", "datetime", "open", "high", "low", "close", "volume",
                           "tradedate", "openprice", "highprice", "lowprice", "closeprice",
                           "adjclose", "vol"} for column in original_columns):
        actions.append("Only recognized OHLCV columns were retained.")

    parsed = _parse_dates(frame["Date"])
    malformed_dates = int(parsed.isna().sum())
    if malformed_dates:
        issues.append(f"{malformed_dates} row(s) contain unparsed timestamps.")
    if parsed.notna().sum() > 1 and not parsed.dropna().is_monotonic_increasing:
        issues.append("Timestamps were unsorted.")
        actions.append("Sorted rows chronologically.")
    frame["Date"] = parsed

    numeric_columns = ("Open", "High", "Low", "Close", "Volume")
    for column in numeric_columns:
        raw_strings = frame[column].astype("string")
        if raw_strings.str.contains(r"[$,\s]", regex=True).fillna(False).any():
            formatted_count = int(raw_strings.str.contains(r"[$,\s]", regex=True).fillna(False).sum())
            issues.append(f"{column} contains formatted numeric text (currency symbol, commas, or whitespace).")
            actions.append(
                f"Sanitized {formatted_count} formatted numeric value(s) in {column}."
            )
        sanitized = (
            raw_strings.str.strip()
            .str.replace(r"[$,\s]", "", regex=True)
            .str.replace(r"\((.*)\)", r"-\1", regex=True)
        )
        converted = pd.to_numeric(sanitized, errors="coerce")
        converted = converted.replace([float("inf"), float("-inf")], pd.NA)
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
    usable_row_count = len(frame)
    if usable_row_count and source_row_count != usable_row_count:
        actions.append(
            f"Extraction/cleaning count: kept {usable_row_count} usable row(s) "
            f"from {source_row_count} source row(s); extracted 6 required OHLCV columns."
        )
    if not issues:
        actions.append("No compatibility issues were detected.")
    elif not actions:
        actions.append("The dataset was inspected; no rows required removal.")
    cleaned = frame.reset_index(drop=True)
    if usable_row_count == source_row_count and not issues:
        actions.append(
            f"Extraction/cleaning count: kept {usable_row_count} usable row(s) "
            f"from {source_row_count} source row(s); extracted 6 required OHLCV columns."
        )
    return CleaningResult(
        cleaned,
        tuple(issues),
        tuple(actions),
        source_row_count=source_row_count,
        usable_row_count=usable_row_count,
    )


def clean_ohlcv_csv(source: str | Path | bytes | BinaryIO | pd.DataFrame) -> CleaningResult:
    """Read a CSV source and return cleaned OHLCV data and a structured summary."""
    if isinstance(source, pd.DataFrame):
        return clean_ohlcv_dataframe(source)
    if isinstance(source, bytes):
        data = pd.read_csv(BytesIO(source))
    elif isinstance(source, str) or isinstance(source, Path):
        try:
            data = pd.read_csv(source)
        except pd.errors.EmptyDataError as error:
            raise ValueError("The uploaded CSV is empty.") from error
        except (UnicodeDecodeError, pd.errors.ParserError) as error:
            raise ValueError("The uploaded CSV could not be parsed.") from error
    else:
        try:
            if hasattr(source, "seek"):
                source.seek(0)
            data = pd.read_csv(source)
        except (AttributeError, UnicodeDecodeError, pd.errors.EmptyDataError,
                pd.errors.ParserError) as error:
            raise ValueError("The uploaded CSV could not be parsed.") from error
    if str(data.columns[0]).strip().lower() == "price":
        try:
            if isinstance(source, bytes):
                raw = pd.read_csv(BytesIO(source), header=None)
            elif isinstance(source, str) or isinstance(source, Path):
                raw = pd.read_csv(source, header=None)
            else:
                if hasattr(source, "seek"):
                    source.seek(0)
                raw = pd.read_csv(source, header=None)
            if len(raw) >= 4:
                columns = ["Date", *[str(value).strip() for value in raw.iloc[0, 1:]]]
                normalized = raw.iloc[3:].copy()
                normalized.columns = columns[: len(normalized.columns)]
                data = normalized
        except (UnicodeDecodeError, pd.errors.EmptyDataError, pd.errors.ParserError):
            pass
    return clean_ohlcv_dataframe(data)
