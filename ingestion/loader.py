"""CSV ingestion and dataset metadata extraction."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ingestion.validator import DatasetMetadata, extract_metadata, validate_ohlcv


def _read_csv(path: Path) -> pd.DataFrame:
    """Read flat CSVs and raw three-row yfinance CSV exports."""
    data = pd.read_csv(path)
    if str(data.columns[0]).strip().lower() == "price":
        raw = pd.read_csv(path, header=None)
        if (
            len(raw) >= 4
            and str(raw.iat[1, 0]).strip().lower() == "ticker"
            and str(raw.iat[2, 0]).strip().lower() == "date"
        ):
            columns = ["Date", *[str(value).strip() for value in raw.iloc[0, 1:]]]
            normalized = raw.iloc[3:].copy()
            normalized.columns = columns[: len(normalized.columns)]
            return normalized
    expected = {"date", "timestamp", "open", "high", "low", "close", "volume"}
    if any(str(column).strip().lower() in expected for column in data.columns):
        return data

    raw = pd.read_csv(path, header=None)
    if len(raw) < 4 or str(raw.iat[0, 0]).strip().lower() != "price":
        return data
    if str(raw.iat[1, 0]).strip().lower() != "ticker":
        return data
    if str(raw.iat[2, 0]).strip().lower() != "date":
        return data
    columns = ["Date", *[str(value).strip() for value in raw.iloc[0, 1:]]]
    normalized = raw.iloc[3:].copy()
    normalized.columns = columns[: len(normalized.columns)]
    return normalized


def load_csv(
    path: str | Path,
    *,
    duplicate_policy: str = "raise",
    instrument: str = "",
    frequency: str = "Daily",
) -> tuple[pd.DataFrame, DatasetMetadata]:
    """Load, validate, and describe an OHLCV CSV file."""
    csv_path = Path(path)
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    notes: list[str] = []
    validated = validate_ohlcv(
        _read_csv(csv_path), duplicate_policy, cleaning_notes=notes
    )
    metadata = extract_metadata(
        validated,
        source=str(csv_path),
        instrument=instrument,
        frequency=frequency,
        cleaning_notes=notes,
    )
    return validated, metadata
