"""CSV ingestion and dataset metadata extraction."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ingestion.validator import DatasetMetadata, extract_metadata, validate_ohlcv


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
        pd.read_csv(csv_path), duplicate_policy, cleaning_notes=notes
    )
    metadata = extract_metadata(
        validated,
        source=str(csv_path),
        instrument=instrument,
        frequency=frequency,
        cleaning_notes=notes,
    )
    return validated, metadata
