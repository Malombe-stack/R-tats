"""CSV exports for simulation outputs."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable

DISCLAIMER = (
    "Simulation only: historical evaluation; results do not guarantee future returns."
)


def export_rows(
    path: str | Path,
    rows: Iterable[dict[str, Any]],
    fieldnames: list[str],
) -> Path:
    """Export dictionaries to CSV with a disclaimer comment."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        handle.write(f"# {DISCLAIMER}\n")
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return destination


def export_run_summary(path: str | Path, rows: Iterable[dict[str, Any]]) -> Path:
    """Export run summary rows with the required disclaimer."""
    rows = list(rows)
    return export_rows(path, rows, list(rows[0]) if rows else ["run_id"])


def export_metrics(path: str | Path, rows: Iterable[dict[str, Any]]) -> Path:
    """Export performance metrics with the required disclaimer."""
    rows = list(rows)
    return export_rows(path, rows, list(rows[0]) if rows else ["metric_name"])


def export_trade_log(path: str | Path, rows: Iterable[dict[str, Any]]) -> Path:
    """Export simulated trades with the required disclaimer."""
    rows = list(rows)
    return export_rows(path, rows, list(rows[0]) if rows else ["trade_id"])
