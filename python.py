"""
Indian Large-Cap Technical + Delivery Screener
================================================
Replicates the manual scan from our conversation:
  - Close > 20 DMA, 50 DMA, 200 DMA
  - Volume > 2x 20-day average volume
  - Delivery % > 60% (today's session)
  - RSI(14) between 55-70
  - New 20-day-high breakout within the last 5 sessions

Data sources:
  - Price / volume / RSI / DMAs  -> yfinance (Yahoo Finance)
  - Delivery %                   -> NSE's daily bhavcopy CSV (sec_bhavdata_full)

WHY NOT nsepython FOR DELIVERY DATA: that package wraps NSE's quote API,
whose JSON schema has changed more than once and breaks silently. Parsing
NSE's published bhavcopy CSV directly (DELIV_PER column) is the same data,
straight from source, with one well-documented format instead of a
third-party wrapper's internals.

WHAT THIS SCRIPT DELIBERATELY DOES NOT DO: predict risk:reward or forward
upside as if they were facts about a stock. Those are levels YOU choose
(reward_risk, min_upside_pct below) -- the script applies your choice
and tells you the resulting quantity/exposure, it doesn't discover one.

REQUIRES LIVE INTERNET ACCESS to query1.finance.yahoo.com and
nsearchives.nseindia.com. Run this on your own machine, not in a
network-sandboxed environment.

Install: pip install yfinance pandas numpy requests
"""

import time
import io
import datetime as dt
import logging
from typing import Optional

import numpy as np
import pandas as pd
import requests
import yfinance as yf

# yfinance can emit noisy 404 / delisted warnings for individual NSE symbols.
# Keep the screen output focused on actual matches and expected skips.
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

# ---------------------------------------------------------------------------
# 1. UNIVERSE -- Nifty 100 constituents as a large-cap proxy.
#    Edit this list if NSE rebalances the index (happens twice a year).
# ---------------------------------------------------------------------------
NIFTY100_SYMBOLS = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "ITC", "SBIN",
    "BHARTIARTL", "LT", "HINDUNILVR", "BAJFINANCE", "KOTAKBANK", "AXISBANK",
    "ASIANPAINT", "MARUTI", "SUNPHARMA", "TITAN", "ULTRACEMCO", "NESTLEIND",
    "ADANIENT", "ADANIPORTS", "WIPRO", "M&M", "NTPC", "POWERGRID", "HCLTECH",
    "BAJAJFINSV", "TATAMOTORS", "TATASTEEL", "JSWSTEEL", "ONGC", "COALINDIA",
    "GRASIM", "TECHM", "INDUSINDBK", "BAJAJ-AUTO", "DRREDDY", "CIPLA",
    "EICHERMOT", "HEROMOTOCO", "HINDALCO", "SBILIFE", "HDFCLIFE", "BRITANNIA",
    "DIVISLAB", "APOLLOHOSP", "SHREECEM", "UPL", "VEDL", "GAIL", "PIDILITIND",
    "DABUR", "GODREJCP", "HAVELLS", "SIEMENS", "TATAPOWER", "TATACONSUM",
    "BANKBARODA", "PNB", "CANBK", "IOC", "BPCL", "ZOMATO", "DMART", "TRENT",
    "LTIM", "BEL", "IRFC", "PFC", "RECLTD", "JIOFIN", "VBL", "ABB",
    "AMBUJACEM", "ADANIGREEN", "ADANIPOWER", "ATGL", "INDIGO", "DLF",
    "LODHA", "PIIND", "TVSMOTOR", "BOSCHLTD", "CHOLAFIN", "SRF",
    "MOTHERSON", "PAGEIND", "TORNTPHARM", "MARICO", "COLPAL", "BERGEPAINT",
    "ICICIPRULI", "ICICIGI", "INDUSTOWER", "NAUKRI", "ZYDUSLIFE", "ALKEM",
    "AUROPHARMA", "LUPIN", "MUTHOOTFIN", "POLYCAB", "SHRIRAMFIN",
    "UNIONBANK", "HAL",
]
TICKERS = [s + ".NS" for s in NIFTY100_SYMBOLS]


# ---------------------------------------------------------------------------
# 2. TECHNICAL FILTERS (yfinance)
# ---------------------------------------------------------------------------
def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def screen_technical(
    ticker: str,
    vol_multiplier: float = 2.0,
    rsi_min: float = 55.0,
    rsi_max: float = 70.0,
    breakout_sessions: int = 5,
    breakout_window: int = 20,
    use_sma20: bool = True,
    use_sma50: bool = True,
    use_sma200: bool = True,
) -> Optional[dict]:
    try:
        df = yf.download(ticker, period="15mo", interval="1d",
                          progress=False, auto_adjust=False)
        if df.empty or len(df) < 210:
            return None
    except Exception as e:
        print(f"  [skip] {ticker}: download failed ({e})")
        return None

    # yfinance can return a MultiIndex column layout depending on version
    # and download settings. Flatten it so indicator math always sees a
    # simple OHLCV dataframe.
    if isinstance(df.columns, pd.MultiIndex):
        if ticker in df.columns.get_level_values(-1):
            df = df.xs(ticker, axis=1, level=-1, drop_level=True)
        else:
            df.columns = df.columns.get_level_values(0)

    df["SMA20"] = df["Close"].rolling(20).mean()
    df["SMA50"] = df["Close"].rolling(50).mean()
    df["SMA200"] = df["Close"].rolling(200).mean()
    df["VolAvg20"] = df["Volume"].rolling(20).mean()
    df["RSI14"] = compute_rsi(df["Close"], 14)
    df[f"High{breakout_window}"] = df["High"].rolling(breakout_window).max().shift(1)

    last = df.iloc[-1]
    last_n = df.iloc[-breakout_sessions:]

    above_dmas = True
    if use_sma20:
        above_dmas = above_dmas and last["Close"] > last["SMA20"]
    if use_sma50:
        above_dmas = above_dmas and last["Close"] > last["SMA50"]
    if use_sma200:
        above_dmas = above_dmas and last["Close"] > last["SMA200"]

    vol_surge = last["Volume"] > vol_multiplier * last["VolAvg20"]
    rsi_in_band = rsi_min <= last["RSI14"] <= rsi_max
    breakout_recent = bool((last_n["Close"] > last_n[f"High{breakout_window}"]).any())

    if not (above_dmas and vol_surge and rsi_in_band and breakout_recent):
        return None

    return {
        "ticker": ticker,
        "close": round(float(last["Close"]), 2),
        "rsi14": round(float(last["RSI14"]), 1),
        "vol_ratio": round(float(last["Volume"] / last["VolAvg20"]), 2),
        "swing_low_5d": round(float(last_n["Low"].min()), 2),
    }


# ---------------------------------------------------------------------------
# 3. DELIVERY % FROM NSE BHAVCOPY
# ---------------------------------------------------------------------------
def get_nse_delivery_data(date: Optional[dt.date] = None) -> pd.DataFrame:
    """
    NSE blocks plain requests without a browser-like User-Agent and a
    warmed-up session cookie. This mimics a real browser hitting the
    homepage first, then the data file. If this 404s, NSE has changed
    the URL pattern again -- check nseindia.com > Reports > Historical
    Data > Securities Bhavcopy for the current path.
    """
    if date is None:
        date = dt.date.today()
    date_str = date.strftime("%d%m%Y")
    url = f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{date_str}.csv"

    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0 Safari/537.36"),
        "Accept-Language": "en-US,en;q=0.9",
    }
    session = requests.Session()
    session.headers.update(headers)
    session.get("https://www.nseindia.com", timeout=10)  # warm up cookies
    time.sleep(1)
    resp = session.get(url, timeout=10)
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text))
    df.columns = [c.strip() for c in df.columns]
    df["SYMBOL"] = df["SYMBOL"].str.strip()
    df["DELIV_PER"] = pd.to_numeric(df["DELIV_PER"], errors="coerce")
    return df[["SYMBOL", "DELIV_PER"]]


def get_delivery_pct(symbol: str, delivery_df: pd.DataFrame) -> Optional[float]:
    row = delivery_df[delivery_df["SYMBOL"] == symbol]
    if row.empty:
        return None
    return float(row.iloc[0]["DELIV_PER"])


# ---------------------------------------------------------------------------
# 4. POSITION SIZING -- turns a passed filter into entry/stop/target.
#    This is arithmetic on numbers YOU choose (risk_pct, reward_risk),
#    not a prediction.
# ---------------------------------------------------------------------------
def position_plan(close: float, swing_low_5d: float, capital: float,
                   risk_pct: float = 1.5, reward_risk: float = 3.0) -> dict:
    entry = close
    stop = swing_low_5d * 0.99  # small buffer below the 5-day swing low
    risk_per_share = entry - stop
    if risk_per_share <= 0:
        return {"error": "swing low is at/above close -- set stop manually"}

    target = entry + reward_risk * risk_per_share
    rupee_risk = capital * (risk_pct / 100)
    qty = int(rupee_risk / risk_per_share)

    return {
        "entry": round(entry, 2),
        "stop_loss": round(stop, 2),
        "target": round(target, 2),
        "expected_upside_pct": round((target - entry) / entry * 100, 2),
        "qty": qty,
        "rupee_risk": round(rupee_risk, 2),
        "rupee_exposure": round(qty * entry, 2),
    }


# ---------------------------------------------------------------------------
# 5. MAIN
# ---------------------------------------------------------------------------
def run_screen(
    capital_for_sizing: float,
    risk_pct: float = 1.5,
    reward_risk: float = 3.0,
    min_upside_pct: float = 8.0,
    min_delivery_pct: float = 60.0,
    vol_multiplier: float = 2.0,
    rsi_min: float = 55.0,
    rsi_max: float = 70.0,
    breakout_sessions: int = 5,
    breakout_window: int = 20,
    use_sma20: bool = True,
    use_sma50: bool = True,
    use_sma200: bool = True,
    progress_callback=None,
):
    print(f"Scanning {len(TICKERS)} large-cap tickers...\n")

    technical_hits = []
    for i, t in enumerate(TICKERS):
        if progress_callback:
            progress_callback(i, len(TICKERS), t)
        result = screen_technical(
            t,
            vol_multiplier=vol_multiplier,
            rsi_min=rsi_min,
            rsi_max=rsi_max,
            breakout_sessions=breakout_sessions,
            breakout_window=breakout_window,
            use_sma20=use_sma20,
            use_sma50=use_sma50,
            use_sma200=use_sma200,
        )
        if result:
            technical_hits.append(result)
        time.sleep(0.3)  # be polite to Yahoo Finance

    print(f"{len(technical_hits)} passed technical filters. Fetching delivery %...\n")

    try:
        delivery_df = get_nse_delivery_data()
    except Exception as e:
        print(f"  [warning] Could not fetch NSE delivery data automatically: {e}")
        print("  Download sec_bhavdata_full CSV manually from nseindia.com "
              "(Reports > Historical Data > Securities Bhavcopy) and load "
              "it with pd.read_csv() using the same column names.")
        delivery_df = pd.DataFrame(columns=["SYMBOL", "DELIV_PER"])

    final = []
    for hit in technical_hits:
        symbol = hit["ticker"].replace(".NS", "")
        deliv = get_delivery_pct(symbol, delivery_df)
        if deliv is None or deliv <= min_delivery_pct:
            continue
        hit["delivery_pct"] = round(deliv, 1)

        plan = position_plan(hit["close"], hit["swing_low_5d"],
                              capital_for_sizing, risk_pct, reward_risk)
        if "error" in plan:
            continue
        if plan["expected_upside_pct"] < min_upside_pct:
            continue

        hit.update(plan)
        final.append(hit)

    final.sort(key=lambda x: x["expected_upside_pct"], reverse=True)

    print(f"\n{len(final)} stocks pass every filter (technical + delivery "
          f"+ your chosen R:R 1:{reward_risk} and >= {min_upside_pct}% upside):\n")

    cols = ["ticker", "close", "rsi14", "vol_ratio", "delivery_pct",
            "entry", "stop_loss", "target", "expected_upside_pct", "qty"]
    if final:
        out_df = pd.DataFrame(final)[cols]
        print(out_df.to_string(index=False))
        out_df.to_csv("screener_results.csv", index=False)
        print("\nSaved to screener_results.csv")
    else:
        print("No stocks passed every filter today. That's a real result, "
              "not a bug -- breakouts that satisfy this many conditions "
              "simultaneously are rare by design. Loosen min_upside_pct or "
              "reward_risk if you want a longer (lower-conviction) list.")

    return final


if __name__ == "__main__":
    # Edit capital_for_sizing to whatever amount you're actually risking --
    # the script doesn't take a position on how much that should be.
    run_screen(capital_for_sizing=30000, risk_pct=1.5,
                reward_risk=3.0, min_upside_pct=8.0)