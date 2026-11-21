# R-TATS

R-TATS is an academic quantitative research and simulation prototype for
event-driven historical backtesting. It supports deterministic OHLCV ingestion,
SMA/EMA crossover and RSI mean-reversion strategies, analytics, SQLite
persistence, CSV export, and a Streamlit dashboard.

## Safety and scope

**Simulation only:** all results are simulated historical evaluations and do not
guarantee future returns. R-TATS contains no brokerage integration, live trading,
real-money order execution, or credential storage.

## Quickstart

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest -q
streamlit run app\main.py
```

The sample dataset is `data\samples\NSE_SAMPLE_DAILY.csv`. The architecture
separates ingestion, strategies, execution, analytics, storage, and presentation.

## Live Cloud Deployment (Streamlit Community Cloud)

1. Push this repository to GitHub.
2. Open [share.streamlit.io](https://share.streamlit.io) and select the
   repository and `main` branch.
3. Set the **Main file path** to `app/main.py`.
4. Select Python **3.12** in the advanced deployment settings.
5. Click **Deploy**. Streamlit installs the pinned dependencies from
   `requirements.txt`.

The application resolves paths from the repository root, creates the local
`data/` directories at startup, and remains simulation-only. Local SQLite
databases are intentionally excluded from Git.
