"""
Exchange market-data adapter.
Uses ccxt for crypto OHLCV research feeds while MT5 remains the only execution path.
"""
from __future__ import annotations

from math import ceil
from typing import Optional

import pandas as pd

try:
    import ccxt  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    ccxt = None


CRYPTO_SYMBOL_PAIRS = {
    "BTCUSD": "BTC/USDT",
}

TIMEFRAME_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
}

TIMEFRAME_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
}


def supports_exchange_symbol(symbol: str) -> bool:
    return symbol.upper() in CRYPTO_SYMBOL_PAIRS


def _parse_lookback_days(lookback: str) -> int:
    raw = (lookback or "5d").strip().lower()
    if raw.endswith("d"):
        return max(1, int(raw[:-1] or "1"))
    if raw.endswith("w"):
        return max(1, int(raw[:-1] or "1")) * 7
    return 5


def _bars_for_request(timeframe: str, lookback: str) -> int:
    days = _parse_lookback_days(lookback)
    minutes = TIMEFRAME_MINUTES.get(timeframe, 15)
    bars = ceil((days * 24 * 60) / minutes)
    return max(120, min(1000, bars + 50))


def fetch_exchange_ohlcv(
    symbol: str,
    timeframe: str,
    lookback: str,
    exchange_id: str = "binance",
) -> Optional[pd.DataFrame]:
    if ccxt is None or not supports_exchange_symbol(symbol):
        return None

    pair = CRYPTO_SYMBOL_PAIRS.get(symbol.upper())
    ccxt_timeframe = TIMEFRAME_MAP.get(timeframe)
    if not pair or not ccxt_timeframe:
        return None

    exchange_cls = getattr(ccxt, exchange_id, None)
    if exchange_cls is None:
        return None

    exchange = exchange_cls({"enableRateLimit": True})
    candles = exchange.fetch_ohlcv(pair, timeframe=ccxt_timeframe, limit=_bars_for_request(timeframe, lookback))
    if not candles:
        return None

    df = pd.DataFrame(candles, columns=["time", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    df.set_index("time", inplace=True)
    return df.dropna(subset=["open", "high", "low", "close"])
