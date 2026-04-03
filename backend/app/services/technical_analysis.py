"""
Real technical analysis using pandas-ta.
Fetches OHLCV data from Yahoo Finance and computes indicators.
"""
import logging
import requests
import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)

YAHOO_URL = "https://query2.finance.yahoo.com/v8/finance/chart/GC%3DF"
HEADERS   = {"User-Agent": "Mozilla/5.0"}


def fetch_ohlcv(interval: str = "15m", range_: str = "5d") -> pd.DataFrame | None:
    """Fetch gold futures OHLCV from Yahoo Finance."""
    try:
        r = requests.get(
            YAHOO_URL,
            params={"interval": interval, "range": range_},
            headers=HEADERS,
            timeout=10,
        )
        r.raise_for_status()
        result = r.json()["chart"]["result"][0]
        timestamps = result["timestamp"]
        q = result["indicators"]["quote"][0]

        df = pd.DataFrame({
            "time":   pd.to_datetime(timestamps, unit="s", utc=True),
            "open":   q["open"],
            "high":   q["high"],
            "low":    q["low"],
            "close":  q["close"],
            "volume": q.get("volume", [0] * len(timestamps)),
        }).dropna(subset=["open", "close"])

        df.set_index("time", inplace=True)
        return df

    except Exception as e:
        logger.error(f"Failed to fetch OHLCV: {e}")
        return None


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute EMA, RSI, MACD, ATR on a DataFrame with open/high/low/close/volume."""
    df = df.copy()
    df.ta.ema(length=9,   append=True)
    df.ta.ema(length=21,  append=True)
    df.ta.ema(length=50,  append=True)
    df.ta.ema(length=200, append=True)
    df.ta.rsi(length=14,  append=True)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    df.ta.atr(length=14,  append=True)
    return df


def analyze_trend(df: pd.DataFrame) -> str:
    """Returns BULLISH, BEARISH, or NEUTRAL based on EMA stack."""
    if len(df) < 50:
        return "NEUTRAL"
    latest = df.iloc[-1]
    e9  = latest.get("EMA_9")
    e21 = latest.get("EMA_21")
    e50 = latest.get("EMA_50")
    if None in (e9, e21, e50):
        return "NEUTRAL"
    if e9 > e21 > e50:
        return "BULLISH"
    if e9 < e21 < e50:
        return "BEARISH"
    return "NEUTRAL"


def get_latest_indicators(interval: str = "15m") -> dict:
    """
    Fetches real OHLCV data and returns the latest indicator values.
    Falls back to safe defaults if data is unavailable.
    """
    df = fetch_ohlcv(interval=interval, range_="5d")
    if df is None or len(df) < 30:
        logger.warning("Insufficient OHLCV data — using fallback indicators.")
        return {
            "RSI_14":       50.0,
            "MACD_12_26_9": 0.0,
            "ATRr_14":      12.0,
            "trend":        "NEUTRAL",
            "current_price": 4750.0,
        }

    df = compute_indicators(df)
    latest = df.iloc[-1]
    trend  = analyze_trend(df)

    return {
        "RSI_14":        round(float(latest.get("RSI_14", 50)),    2),
        "MACD_12_26_9":  round(float(latest.get("MACDh_12_26_9", 0)), 4),
        "ATRr_14":       round(float(latest.get("ATRr_14", 12)),   2),
        "EMA_9":         round(float(latest.get("EMA_9",  0)),     2),
        "EMA_21":        round(float(latest.get("EMA_21", 0)),     2),
        "EMA_50":        round(float(latest.get("EMA_50", 0)),     2),
        "trend":         trend,
        "current_price": round(float(latest["close"]),             2),
    }
