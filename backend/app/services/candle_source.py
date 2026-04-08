"""
Unified candle source abstraction.
Prefers live MT5 bars when available and falls back to Yahoo Finance.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
from math import ceil
from typing import Optional

import pandas as pd

from app.services.technical_analysis import fetch_ohlcv as fetch_yahoo_ohlcv

logger = logging.getLogger(__name__)

try:
    import MetaTrader5 as mt5  # type: ignore
except Exception:  # pragma: no cover - optional dependency in tests
    mt5 = None


_MT5_TIMEFRAMES = {
    "1m": "TIMEFRAME_M1",
    "5m": "TIMEFRAME_M5",
    "15m": "TIMEFRAME_M15",
    "1h": "TIMEFRAME_H1",
    "4h": "TIMEFRAME_H4",
}

_TIMEFRAME_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
}


@dataclass
class CandleSourceResult:
    df: pd.DataFrame
    symbol: str
    timeframe: str
    lookback: str
    source: str
    is_live: bool
    confidence_cap: float
    notes: list[str]


def _parse_lookback_days(lookback: str) -> int:
    raw = (lookback or "5d").strip().lower()
    if raw.endswith("d"):
        return max(1, int(raw[:-1] or "1"))
    if raw.endswith("w"):
        return max(1, int(raw[:-1] or "1")) * 7
    return 5


def _bars_for_request(timeframe: str, lookback: str) -> int:
    days = _parse_lookback_days(lookback)
    minutes = _TIMEFRAME_MINUTES.get(timeframe, 15)
    bars = ceil((days * 24 * 60) / minutes)
    return max(120, bars + 50)


def _fetch_mt5_ohlcv(symbol: str, timeframe: str, lookback: str) -> Optional[pd.DataFrame]:
    if mt5 is None:
        return None

    try:
        if mt5.terminal_info() is None:
            return None

        tf_name = _MT5_TIMEFRAMES.get(timeframe)
        if not tf_name:
            return None

        tf = getattr(mt5, tf_name, None)
        if tf is None:
            return None

        mt5.symbol_select(symbol, True)
        count = _bars_for_request(timeframe, lookback)
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None or len(rates) == 0:
            return None

        df = pd.DataFrame(rates)
        if df.empty:
            return None

        volume_col = "tick_volume" if "tick_volume" in df.columns else "real_volume"
        df = df.rename(columns={volume_col: "volume"})
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df[["time", "open", "high", "low", "close", "volume"]]
        df.set_index("time", inplace=True)
        return df.dropna(subset=["open", "high", "low", "close"])
    except Exception as exc:
        logger.warning(f"MT5 candle fetch failed for {symbol} {timeframe}: {exc}")
        return None


def fetch_candles(symbol: str, timeframe: str, lookback: str) -> Optional[CandleSourceResult]:
    """
    Fetch candles from the best available source.
    MT5 is preferred because it is live and uses the broker symbol's actual volume profile.
    """
    mt5_df = _fetch_mt5_ohlcv(symbol, timeframe, lookback)
    if mt5_df is not None and len(mt5_df) >= 50:
        return CandleSourceResult(
            df=mt5_df,
            symbol=symbol,
            timeframe=timeframe,
            lookback=lookback,
            source="mt5",
            is_live=True,
            confidence_cap=98.0,
            notes=["live_source", "broker_volume"],
        )

    yahoo_df = fetch_yahoo_ohlcv(interval=timeframe, range_=lookback, symbol=symbol)
    if yahoo_df is not None and len(yahoo_df) >= 50:
        return CandleSourceResult(
            df=yahoo_df,
            symbol=symbol,
            timeframe=timeframe,
            lookback=lookback,
            source="yahoo",
            is_live=False,
            confidence_cap=84.0,
            notes=["delayed_source", "confidence_capped"],
        )

    return None
