# R-TATS User Guide

R-TATS is an academic, simulation-only backtesting prototype. It
loads historical OHLCV data, validates it, runs an event-driven Backtrader
strategy, calculates deterministic performance metrics, and stores/export the
results. It never connects to a broker, places real orders, or stores
credentials.

## Install and start

From the project directory on Windows:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app\main.py
```

Run the automated checks with `pytest -q`.

## Data

Use the bundled `data\samples\NSE_SAMPLE_DAILY.csv` or upload a CSV containing
`timestamp` (or `date`), `open`, `high`, `low`, `close`, and `volume`. Names are
case-insensitive. Dates must be parseable, prices must be non-negative, volume
must be non-negative, and `high` must be at least every other price. Duplicate
timestamps fail by default; `drop_first` is available for an explicitly
recorded cleaning policy. Out-of-order rows are sorted and noted in metadata.

## Strategies

* **SMA Crossover:** buys when a fast simple moving average crosses above a
  slower average and exits on the reverse cross.
* **EMA Crossover:** the same signal using exponentially weighted averages.
* **RSI:** buys below the oversold threshold and exits above the overbought
  threshold.

Signals use closed bars and Backtrader executes orders on the next bar. Position
size is limited to the configured percentage of available cash.

## Metrics and results

The dashboard shows total return, Sharpe ratio, maximum drawdown, win rate,
profit factor, and completed trades. Undefined metrics are shown as
`N/A — <reason>` rather than infinity or a misleading zero. Equity, underwater
drawdown, price/indicator, and trade-marker charts are intended for historical
evaluation, not forecasting.

Results can be exported as CSV with a simulation disclaimer. SQLite persistence
uses `data\backtests.db` when configured by an application integration and
contains run metadata, metrics, and simulated trades.

## Academic limitations

This is a deterministic research and teaching prototype. Historical results
are simulated evaluations and do not guarantee future returns. Slippage,
commission assumptions, data quality, and model choices can materially affect
results. Do not enter brokerage credentials or treat output as investment
advice.
