"""
Real technical analysis using pandas-ta.
Fetches OHLCV data from Yahoo Finance and computes indicators.
<<<<<<< HEAD
Supports multiple symbols via configurable Yahoo tickers.
=======
>>>>>>> 43c9f1b194f748ead11d6ed556a8f6ef5941c6e1
"""
import logging
import requests
import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)

<<<<<<< HEAD
# Symbol → Yahoo Finance ticker mapping
SYMBOL_TICKERS = {
    "XAUUSD": "GC%3DF",       # Gold Futures
    "XAGUSD": "SI%3DF",       # Silver Futures
    "EURUSD": "EURUSD%3DX",   # EUR/USD
    "GBPUSD": "GBPUSD%3DX",   # GBP/USD
    "USDJPY": "JPY%3DX",      # USD/JPY
    "BTCUSD": "BTC-USD",      # Bitcoin
}

YAHOO_BASE = "https://query2.finance.yahoo.com/v8/finance/chart/"
HEADERS    = {"User-Agent": "Mozilla/5.0"}


def _get_yahoo_url(symbol: str = "XAUUSD") -> str:
    """Resolve symbol to Yahoo Finance URL."""
    ticker = SYMBOL_TICKERS.get(symbol.upper(), "GC%3DF")
    return f"{YAHOO_BASE}{ticker}"


def fetch_ohlcv(interval: str = "15m", range_: str = "5d", symbol: str = "XAUUSD") -> pd.DataFrame | None:
    """Fetch OHLCV data from Yahoo Finance for any supported symbol."""
    try:
        url = _get_yahoo_url(symbol)
        r = requests.get(
            url,
=======
YAHOO_URL = "https://query2.finance.yahoo.com/v8/finance/chart/GC%3DF"
HEADERS   = {"User-Agent": "Mozilla/5.0"}


def fetch_ohlcv(interval: str = "15m", range_: str = "5d") -> pd.DataFrame | None:
    """Fetch gold futures OHLCV from Yahoo Finance."""
    try:
        r = requests.get(
            YAHOO_URL,
>>>>>>> 43c9f1b194f748ead11d6ed556a8f6ef5941c6e1
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
<<<<<<< HEAD
        logger.error(f"Failed to fetch OHLCV for {symbol}: {e}")
=======
        logger.error(f"Failed to fetch OHLCV: {e}")
>>>>>>> 43c9f1b194f748ead11d6ed556a8f6ef5941c6e1
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


<<<<<<< HEAD
def get_latest_indicators(interval: str = "15m", symbol: str = "XAUUSD") -> dict:
=======
def get_latest_indicators(interval: str = "15m") -> dict:
>>>>>>> 43c9f1b194f748ead11d6ed556a8f6ef5941c6e1
    """
    Fetches real OHLCV data and returns the latest indicator values.
    Falls back to safe defaults if data is unavailable.
    """
<<<<<<< HEAD
    df = fetch_ohlcv(interval=interval, range_="5d", symbol=symbol)
    if df is None or len(df) < 30:
        logger.warning(f"Insufficient OHLCV data for {symbol} — using fallback indicators.")
=======
    df = fetch_ohlcv(interval=interval, range_="5d")
    if df is None or len(df) < 30:
        logger.warning("Insufficient OHLCV data — using fallback indicators.")
>>>>>>> 43c9f1b194f748ead11d6ed556a8f6ef5941c6e1
        return {
            "RSI_14":       50.0,
            "MACD_12_26_9": 0.0,
            "ATRr_14":      12.0,
            "trend":        "NEUTRAL",
            "current_price": 4750.0,
<<<<<<< HEAD
            "symbol":       symbol,
=======
>>>>>>> 43c9f1b194f748ead11d6ed556a8f6ef5941c6e1
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
<<<<<<< HEAD
        "symbol":        symbol,
=======
>>>>>>> 43c9f1b194f748ead11d6ed556a8f6ef5941c6e1
    }
