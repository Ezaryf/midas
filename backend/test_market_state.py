import unittest

import pandas as pd

from app.core.loop import STYLE_CONFIG
from app.services.market_state import build_analysis_batch, build_snapshot


def make_df(closes: list[float], volume_base: float = 1000) -> pd.DataFrame:
    rows = []
    previous = closes[0]
    for index, close in enumerate(closes):
        open_ = previous
        high = max(open_, close) + 0.8
        low = min(open_, close) - 0.8
        volume = volume_base + index * 5
        rows.append(
            {
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )
        previous = close

    df = pd.DataFrame(rows)
    df.index = pd.date_range("2026-01-01", periods=len(df), freq="min", tz="UTC")
    df["EMA_9"] = df["close"].ewm(span=9, adjust=False).mean()
    df["EMA_21"] = df["close"].ewm(span=21, adjust=False).mean()
    df["EMA_50"] = df["close"].ewm(span=50, adjust=False).mean()
    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, 1e-9)
    df["RSI_14"] = 100 - (100 / (1 + rs))
    ema_fast = df["close"].ewm(span=12, adjust=False).mean()
    ema_slow = df["close"].ewm(span=26, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal = macd.ewm(span=9, adjust=False).mean()
    df["MACDh_12_26_9"] = macd - signal
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["ATRr_14"] = tr.rolling(14).mean().bfill()
    return df


def make_snapshots(primary_closes: list[float], secondary_closes: list[float] | None = None):
    secondary_closes = secondary_closes or primary_closes
    primary_df = make_df(primary_closes)
    secondary_df = make_df(secondary_closes)
    current_price = float(primary_df.iloc[-1]["close"])
    return {
        "5m": build_snapshot(primary_df, "5m", "mt5", True, current_price),
        "1m": build_snapshot(secondary_df, "1m", "mt5", True, current_price),
    }


class MarketStateEngineTests(unittest.TestCase):
    def test_detects_breakout_continuation(self):
        closes = [100.0] * 18 + [100.2, 100.1, 100.3, 100.2, 100.4, 101.0, 102.2, 103.4, 104.0]
        batch = build_analysis_batch(
            symbol="XAUUSD",
            style="Scalper",
            snapshots=make_snapshots(closes),
            style_cfg=STYLE_CONFIG["Scalper"],
            patterns_by_timeframe={"5m": [], "1m": []},
        )
        self.assertEqual(batch.primary.direction, "BUY")
        self.assertEqual(batch.primary.setup_type, "breakout_continuation")

    def test_detects_pullback_continuation(self):
        closes = [100 + i * 0.15 for i in range(14)] + [102.8, 103.5, 104.1, 103.6, 103.2, 103.0, 103.4, 103.8]
        batch = build_analysis_batch(
            symbol="XAUUSD",
            style="Scalper",
            snapshots=make_snapshots(closes),
            style_cfg=STYLE_CONFIG["Scalper"],
            patterns_by_timeframe={"5m": [], "1m": []},
        )
        self.assertEqual(batch.primary.direction, "BUY")
        self.assertIn(batch.primary.setup_type, {"pullback_continuation", "breakout_continuation"})

    def test_detects_validated_range_reversion(self):
        closes = [100, 101, 102, 103, 102, 101, 100, 99, 100, 101, 102, 103, 102, 101, 100, 99.4, 99.2]
        batch = build_analysis_batch(
            symbol="EURUSD",
            style="Intraday",
            snapshots={
                "15m": build_snapshot(make_df(closes), "15m", "mt5", True, closes[-1]),
                "1h": build_snapshot(make_df(closes), "1h", "mt5", True, closes[-1]),
            },
            style_cfg=STYLE_CONFIG["Intraday"],
            patterns_by_timeframe={"15m": [], "1h": []},
        )
        self.assertEqual(batch.primary.market_regime, "range")
        self.assertIn(batch.primary.setup_type, {"range_reversion_long", "range_reversion_short"})

    def test_detects_exhaustion_reversal(self):
        closes = [100 + i * 0.3 for i in range(16)] + [105.5, 106.2, 107.0, 107.8, 107.1]
        df = make_df(closes, volume_base=1500)
        # Force an obvious exhaustion wick on the last candle.
        df.iloc[-1, df.columns.get_loc("high")] = 109.8
        df.iloc[-1, df.columns.get_loc("close")] = 107.1
        df.iloc[-1, df.columns.get_loc("open")] = 107.9
        batch = build_analysis_batch(
            symbol="BTCUSD",
            style="Intraday",
            snapshots={
                "15m": build_snapshot(df, "15m", "mt5", True, float(df.iloc[-1]["close"])),
                "1h": build_snapshot(df, "1h", "mt5", True, float(df.iloc[-1]["close"])),
            },
            style_cfg=STYLE_CONFIG["Intraday"],
            patterns_by_timeframe={"15m": [], "1h": []},
        )
        self.assertEqual(batch.primary.direction, "SELL")
        self.assertEqual(batch.primary.setup_type, "exhaustion_reversal_short")

    def test_detects_lower_high_failure_or_breakdown(self):
        closes = [100 + i * 0.3 for i in range(10)] + [103.8, 104.2, 103.7, 103.1, 103.6, 103.0, 102.4, 101.9, 101.4]
        batch = build_analysis_batch(
            symbol="GBPUSD",
            style="Scalper",
            snapshots=make_snapshots(closes),
            style_cfg=STYLE_CONFIG["Scalper"],
            patterns_by_timeframe={"5m": [], "1m": []},
        )
        self.assertEqual(batch.primary.direction, "SELL")
        self.assertIn(batch.primary.setup_type, {"lower_high_failure", "breakdown_retest"})

    def test_returns_hold_when_no_setup_survives(self):
        closes = [100.0 + (0.02 if index % 2 == 0 else -0.02) for index in range(24)]
        batch = build_analysis_batch(
            symbol="XAGUSD",
            style="Swing",
            snapshots={
                "1h": build_snapshot(make_df(closes), "1h", "mt5", True, closes[-1]),
                "4h": build_snapshot(make_df(closes), "4h", "mt5", True, closes[-1]),
            },
            style_cfg=STYLE_CONFIG["Swing"],
            patterns_by_timeframe={"1h": [], "4h": []},
        )
        self.assertEqual(batch.primary.direction, "HOLD")
        self.assertEqual(batch.primary.setup_type, "no_trade")


if __name__ == "__main__":
    unittest.main()
