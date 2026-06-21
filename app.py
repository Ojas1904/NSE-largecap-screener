"""
NSE Large-Cap Screener — Streamlit UI
Run with:  streamlit run app.py
"""

import streamlit as st
import pandas as pd
from python import run_screen

st.set_page_config(page_title="NSE Large-Cap Screener", layout="wide")
st.title("NSE Large-Cap Screener")
st.caption("Edit filters in the sidebar, then click **Run Screener**.")

# ---------------------------------------------------------------------------
# Sidebar — all editable filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Technical Filters")

    st.subheader("Moving Averages")
    use_sma20 = st.checkbox("Close > 20 DMA", value=True)
    use_sma50 = st.checkbox("Close > 50 DMA", value=True)
    use_sma200 = st.checkbox("Close > 200 DMA", value=True)

    st.subheader("Volume")
    vol_multiplier = st.number_input(
        "Volume > N × 20-day avg", min_value=0.5, max_value=10.0,
        value=2.0, step=0.25,
        help="e.g. 2.0 means today's volume must be > 2× the 20-day average"
    )

    st.subheader("RSI (14)")
    rsi_col1, rsi_col2 = st.columns(2)
    with rsi_col1:
        rsi_min = st.number_input("Min RSI", min_value=0, max_value=100, value=55)
    with rsi_col2:
        rsi_max = st.number_input("Max RSI", min_value=0, max_value=100, value=70)

    st.subheader("Breakout")
    breakout_window = st.number_input(
        "N-day high window", min_value=5, max_value=60, value=20, step=1,
        help="Breakout is defined as closing above the prior N-day high"
    )
    breakout_sessions = st.number_input(
        "Breakout within last N sessions", min_value=1, max_value=20, value=5, step=1,
        help="The breakout must have occurred within the last N sessions"
    )

    st.divider()
    st.header("Delivery Filter")
    min_delivery_pct = st.number_input(
        "Min Delivery %", min_value=0.0, max_value=100.0,
        value=60.0, step=1.0,
        help="NSE bhavcopy DELIV_PER — fraction of traded volume that was delivery-based"
    )

    st.divider()
    st.header("Position Sizing")
    capital = st.number_input(
        "Capital (₹)", min_value=1000, value=30000, step=1000
    )
    risk_pct = st.number_input(
        "Risk per trade (%)", min_value=0.1, max_value=10.0,
        value=1.5, step=0.1,
        help="Percentage of capital you are willing to lose on this trade"
    )
    reward_risk = st.number_input(
        "Reward : Risk ratio", min_value=1.0, max_value=10.0,
        value=3.0, step=0.5,
        help="Target is set at this multiple of the risk amount"
    )
    min_upside_pct = st.number_input(
        "Min expected upside (%)", min_value=0.0, max_value=50.0,
        value=8.0, step=0.5
    )

# ---------------------------------------------------------------------------
# Active filter summary (main area)
# ---------------------------------------------------------------------------
with st.expander("Active filter summary", expanded=False):
    active = []
    if use_sma20:  active.append("Close > 20 DMA")
    if use_sma50:  active.append("Close > 50 DMA")
    if use_sma200: active.append("Close > 200 DMA")
    active.append(f"Volume > {vol_multiplier}× 20-day avg")
    active.append(f"RSI(14) between {rsi_min}–{rsi_max}")
    active.append(f"Broke {breakout_window}-day high within last {breakout_sessions} sessions")
    active.append(f"Delivery % > {min_delivery_pct}%")
    active.append(f"Expected upside ≥ {min_upside_pct}%  |  R:R 1:{reward_risk}  |  Risk {risk_pct}% of ₹{capital:,}")
    for f in active:
        st.markdown(f"- {f}")

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if rsi_min >= rsi_max:
    st.error("RSI Min must be less than RSI Max.")
    st.stop()

run_btn = st.button("Run Screener", type="primary", use_container_width=True)

if run_btn:
    progress_bar = st.progress(0, text="Starting scan…")
    status_text = st.empty()

    def on_progress(i, total, ticker):
        pct = int((i / total) * 100)
        progress_bar.progress(pct, text=f"Scanning {ticker} ({i+1}/{total})")
        status_text.text(f"Checking {ticker}…")

    with st.spinner("Running screener (this takes a few minutes)…"):
        results = run_screen(
            capital_for_sizing=float(capital),
            risk_pct=float(risk_pct),
            reward_risk=float(reward_risk),
            min_upside_pct=float(min_upside_pct),
            min_delivery_pct=float(min_delivery_pct),
            vol_multiplier=float(vol_multiplier),
            rsi_min=float(rsi_min),
            rsi_max=float(rsi_max),
            breakout_sessions=int(breakout_sessions),
            breakout_window=int(breakout_window),
            use_sma20=use_sma20,
            use_sma50=use_sma50,
            use_sma200=use_sma200,
            progress_callback=on_progress,
        )

    progress_bar.progress(100, text="Done!")
    status_text.empty()

    if not results:
        st.warning(
            "No stocks passed every filter today. "
            "Try loosening min upside %, delivery %, or RSI band."
        )
    else:
        st.success(f"{len(results)} stock(s) passed all filters.")

        cols = ["ticker", "close", "rsi14", "vol_ratio", "delivery_pct",
                "entry", "stop_loss", "target", "expected_upside_pct", "qty", "rupee_exposure"]
        df = pd.DataFrame(results)[cols]
        df = df.rename(columns={
            "ticker": "Ticker",
            "close": "Close",
            "rsi14": "RSI(14)",
            "vol_ratio": "Vol Ratio",
            "delivery_pct": "Delivery %",
            "entry": "Entry",
            "stop_loss": "Stop Loss",
            "target": "Target",
            "expected_upside_pct": "Upside %",
            "qty": "Qty",
            "rupee_exposure": "Exposure (₹)",
        })

        st.dataframe(
            df.style.format({
                "Close": "₹{:.2f}", "Entry": "₹{:.2f}",
                "Stop Loss": "₹{:.2f}", "Target": "₹{:.2f}",
                "Upside %": "{:.1f}%", "Vol Ratio": "{:.2f}x",
                "Delivery %": "{:.1f}%", "RSI(14)": "{:.1f}",
                "Exposure (₹)": "₹{:,.0f}",
            }),
            use_container_width=True,
            hide_index=True,
        )

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download CSV", data=csv,
            file_name="screener_results.csv", mime="text/csv"
        )
