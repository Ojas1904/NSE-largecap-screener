# NSE Large-Cap Screener

A technical + delivery screener for Nifty 100 stocks with an interactive Streamlit UI to customize filters without touching the code.

## What it screens for

| Filter | Default |
|--------|---------|
| Close > 20 / 50 / 200 DMA | All three on |
| Volume surge | > 2× 20-day average |
| RSI (14) | 55 – 70 |
| Breakout | New N-day high within last 5 sessions |
| NSE Delivery % | > 60% |
| Expected upside | ≥ 8% at chosen R:R |

All filters are editable from the UI sidebar — no code changes needed.

## Setup

```bash
pip install yfinance pandas numpy requests streamlit
```

## Run

```bash
python -m streamlit run app.py
```

Opens in your browser at `http://localhost:8501`.  
Adjust any filter in the sidebar and click **Run Screener**.

To run headless (no UI):

```bash
python python.py
```

## Data sources

- **Price / volume / RSI / DMAs** — Yahoo Finance via `yfinance`
- **Delivery %** — NSE daily bhavcopy CSV (`sec_bhavdata_full`) fetched directly from `nsearchives.nseindia.com`

Requires live internet access.

## Output

Results are displayed in the browser table and can be downloaded as `screener_results.csv`.

Columns: `Ticker · Close · RSI(14) · Vol Ratio · Delivery % · Entry · Stop Loss · Target · Upside % · Qty · Exposure (₹)`
