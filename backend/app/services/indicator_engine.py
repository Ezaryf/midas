"""
Indicator engine abstraction.
Prefers TA-Lib when available and falls back to pandas-ta or pandas-native calculations.
"""
from __future__ import annotations

import logging
from typing import Literal

import pandas as pd

logger = logging.getLogger(__name__)

try:
    import talib  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    talib = None

try:
    import pandas_ta as pandas_ta  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pandas_ta = None


IndicatorEngine = Literal["ta-lib", "pandas-ta", "pandas-native"]


def get_indicator_engine() -> IndicatorEngine:
    if talib is not None:
        return "ta-lib"
    if pandas_ta is not None:
        return "pandas-ta"
    return "pandas-native"


def _native_rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)


def _native_atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute EMA, RSI, MACD, and ATR with a stable column contract.
    """
    result = df.copy()
    close = result["close"].astype(float)
    high = result["high"].astype(float)
    low = result["low"].astype(float)

    engine = get_indicator_engine()
    if engine == "ta-lib":
        result["EMA_9"] = talib.EMA(close, timeperiod=9)
        result["EMA_21"] = talib.EMA(close, timeperiod=21)
        result["EMA_50"] = talib.EMA(close, timeperiod=50)
        result["EMA_200"] = talib.EMA(close, timeperiod=200)
        result["RSI_14"] = talib.RSI(close, timeperiod=14)
        macd, macd_signal, macd_hist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
        result["MACD_12_26_9"] = macd
        result["MACDs_12_26_9"] = macd_signal
        result["MACDh_12_26_9"] = macd_hist
        result["ATRr_14"] = talib.ATR(high, low, close, timeperiod=14)
        return result

    if engine == "pandas-ta":
        temp = result.copy()
        temp.ta.ema(length=9, append=True)
        temp.ta.ema(length=21, append=True)
        temp.ta.ema(length=50, append=True)
        temp.ta.ema(length=200, append=True)
        temp.ta.rsi(length=14, append=True)
        temp.ta.macd(fast=12, slow=26, signal=9, append=True)
        temp.ta.atr(length=14, append=True)
        return temp

    logger.warning("TA-Lib and pandas-ta unavailable - using pandas-native indicators")
    result["EMA_9"] = close.ewm(span=9, adjust=False).mean()
    result["EMA_21"] = close.ewm(span=21, adjust=False).mean()
    result["EMA_50"] = close.ewm(span=50, adjust=False).mean()
    result["EMA_200"] = close.ewm(span=200, adjust=False).mean()
    result["RSI_14"] = _native_rsi(close, 14)

    ema_fast = close.ewm(span=12, adjust=False).mean()
    ema_slow = close.ewm(span=26, adjust=False).mean()
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    result["MACD_12_26_9"] = macd
    result["MACDs_12_26_9"] = macd_signal
    result["MACDh_12_26_9"] = macd - macd_signal
    result["ATRr_14"] = _native_atr(high, low, close, 14)
    return result
