"""Fetch and normalize historical benchmark and Nairobi exchange data."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

import pandas as pd
import yfinance as yf

OUTPUT_DIR: Final[Path] = Path(__file__).resolve().parents[1] / "data" / "samples"
DATASETS: Final[tuple[tuple[str, str, str], ...]] = (
    ("SPY", "10y", "SPY_10Y_DAILY.csv"),
    ("SCOM.NR", "5y", "SCOM_NR_5Y_DAILY.csv"),
    ("EQTY.NR", "5y", "EQTY_NR_5Y_DAILY.csv"),
    ("KCB.NR", "5y", "KCB_NR_5Y_DAILY.csv"),
    ("COOP.NR", "5y", "COOP_NR_5Y_DAILY.csv"),
    ("EABL.NR", "5y", "EABL_NR_5Y_DAILY.csv"),
)
LOGGER = logging.getLogger(__name__)


def normalize_download(data: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Normalize a yfinance frame to the application's canonical CSV schema.

    Args:
        data: Raw frame returned by ``yfinance.download``.

    Returns:
        A normalized frame and the number of zero-volume days created.

    Raises:
        ValueError: If a non-empty frame does not contain the required fields.
    """
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [
            col[0] if isinstance(col, tuple) else col for col in data.columns
        ]
    result = data.reset_index()
    result = result.drop(columns=["Adj Close"], errors="ignore")
    aliases = {
        ("timestamp" if str(column).strip().lower() in {"date", "timestamp"}
         else str(column).strip().lower()): column
        for column in result.columns
    }
    required = ("timestamp", "open", "high", "low", "close", "volume")
    missing = [column for column in required if column not in aliases]
    if missing:
        raise ValueError(f"Downloaded data is missing columns: {', '.join(missing)}")
    result = result[[aliases[column] for column in required]].copy()
    result.columns = list(required)
    result["timestamp"] = pd.to_datetime(result["timestamp"], errors="coerce")
    for column in ("open", "high", "low", "close", "volume"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result = result.loc[result["close"].notna() & (result["close"] > 0)]
    zero_volume_days = int(result["volume"].isna().sum())
    if zero_volume_days:
        LOGGER.info("Filling %d zero-volume days.", zero_volume_days)
        result["volume"] = result["volume"].fillna(0)
    result = result.dropna(subset=["timestamp"])
    result["timestamp"] = result["timestamp"].dt.strftime("%Y-%m-%d")
    result = (
        result.sort_values("timestamp")
        .drop_duplicates("timestamp", keep="first")
        .reset_index(drop=True)
    )
    return result, zero_volume_days


def fetch_dataset(symbol: str, period: str, filename: str) -> dict[str, object] | None:
    """Download, normalize, and save one symbol's historical dataset."""
    LOGGER.info("Downloading %s (%s).", symbol, period)
    data = yf.download(
        symbol,
        period=period,
        interval="1d",
        multi_level_index=False,
        auto_adjust=False,
        progress=False,
    )
    if data.empty:
        LOGGER.warning("No data returned for %s; skipping %s.", symbol, filename)
        return None
    normalized, zero_volume_days = normalize_download(data)
    if normalized.empty:
        LOGGER.warning("No usable rows returned for %s; skipping %s.", symbol, filename)
        return None
    output = OUTPUT_DIR / filename
    normalized.to_csv(output, index=False)
    return {
        "filename": filename,
        "rows": len(normalized),
        "start": normalized["timestamp"].iloc[0],
        "end": normalized["timestamp"].iloc[-1],
        "zero_volume_days": zero_volume_days,
    }


def main() -> None:
    """Fetch all configured datasets and print a generation summary."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summaries = [
        summary
        for symbol, period, filename in DATASETS
        if (summary := fetch_dataset(symbol, period, filename)) is not None
    ]
    print("\nGenerated CSV summary")
    print("filename | rows | start date | end date | zero-volume days")
    for summary in summaries:
        print(
            f"{summary['filename']} | {summary['rows']} | {summary['start']} | "
            f"{summary['end']} | {summary['zero_volume_days']}"
        )


if __name__ == "__main__":
    main()
