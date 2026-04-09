"""
Technical analysis service with a pluggable indicator engine.
Fetches OHLCV data from Yahoo Finance and computes indicators.
"""
import logging
import requests
import pandas as pd

from app.services.indicator_engine import compute_indicators as compute_indicator_set
from app.services.indicator_engine import get_indicator_engine

logger = logging.getLogger(__name__)

SYMBOL_TICKERS = {
    "XAUUSD": "GC%3DF",
    "XAGUSD": "SI%3DF",
    "EURUSD": "EURUSD%3DX",
    "GBPUSD": "GBPUSD%3DX",
    "USDJPY": "JPY%3DX",
    "BTCUSD": "BTC-USD",
}

YAHOO_BASE = "https://query2.finance.yahoo.com/v8/finance/chart/"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def _get_yahoo_url(symbol: str = "XAUUSD") -> str:
    ticker = SYMBOL_TICKERS.get(symbol.upper(), "GC%3DF")
    return f"{YAHOO_BASE}{ticker}"


def fetch_ohlcv(interval: str = "15m", range_: str = "5d", symbol: str = "XAUUSD") -> pd.DataFrame | None:
    try:
        url = _get_yahoo_url(symbol)
        response = requests.get(
            url,
            params={"interval": interval, "range": range_},
            headers=HEADERS,
            timeout=10,
        )
        response.raise_for_status()
        result = response.json()["chart"]["result"][0]
        timestamps = result["timestamp"]
        quote = result["indicators"]["quote"][0]

        df = pd.DataFrame({
            "time": pd.to_datetime(timestamps, unit="s", utc=True),
            "open": quote["open"],
            "high": quote["high"],
            "low": quote["low"],
            "close": quote["close"],
            "volume": quote.get("volume", [0] * len(timestamps)),
        }).dropna(subset=["open", "close"])

        df.set_index("time", inplace=True)
        return df
    except Exception as exc:
        logger.error(f"Failed to fetch OHLCV for {symbol}: {exc}")
        return None


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    enriched = compute_indicator_set(df)
    enriched.attrs["indicator_engine"] = get_indicator_engine()
    return enriched


def analyze_trend(df: pd.DataFrame) -> str:
    if len(df) < 50:
        return "NEUTRAL"
    latest = df.iloc[-1]
    e9 = latest.get("EMA_9")
    e21 = latest.get("EMA_21")
    e50 = latest.get("EMA_50")
    if None in (e9, e21, e50):
        return "NEUTRAL"
    if e9 > e21 > e50:
        return "BULLISH"
    if e9 < e21 < e50:
        return "BEARISH"
    return "NEUTRAL"


def get_latest_indicators(interval: str = "15m", symbol: str = "XAUUSD") -> dict:
    df = fetch_ohlcv(interval=interval, range_="5d", symbol=symbol)
    if df is None or len(df) < 30:
        logger.warning(f"Insufficient OHLCV data for {symbol} - using fallback indicators.")
        return {
            "RSI_14": 50.0,
            "MACD_12_26_9": 0.0,
            "ATRr_14": 12.0,
            "trend": "NEUTRAL",
            "current_price": 4750.0,
            "symbol": symbol,
            "indicator_engine": get_indicator_engine(),
        }

    df = compute_indicators(df)
    latest = df.iloc[-1]
    trend = analyze_trend(df)

    return {
        "RSI_14": round(float(latest.get("RSI_14", 50)), 2),
        "MACD_12_26_9": round(float(latest.get("MACDh_12_26_9", 0)), 4),
        "ATRr_14": round(float(latest.get("ATRr_14", 12)), 2),
        "EMA_9": round(float(latest.get("EMA_9", 0)), 2),
        "EMA_21": round(float(latest.get("EMA_21", 0)), 2),
        "EMA_50": round(float(latest.get("EMA_50", 0)), 2),
        "trend": trend,
        "current_price": round(float(latest["close"]), 2),
        "symbol": symbol,
        "indicator_engine": df.attrs.get("indicator_engine", get_indicator_engine()),
    }
