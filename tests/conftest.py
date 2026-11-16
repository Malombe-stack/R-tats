"""Shared deterministic test fixtures."""

from pathlib import Path

import pandas as pd
import pytest

from ingestion.loader import load_csv


@pytest.fixture
def sample_path() -> Path:
    """Return the deterministic sample path."""
    return Path(__file__).parents[1] / "data" / "samples" / "NSE_SAMPLE_DAILY.csv"


@pytest.fixture
def valid_data(sample_path: Path) -> pd.DataFrame:
    """Load the valid sample dataset."""
    return load_csv(sample_path)[0]
